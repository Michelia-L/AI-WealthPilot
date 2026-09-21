"""Resource migrations preserve payloads and never infer permissions from names."""

import json

import pytest
from sqlalchemy import event, inspect
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session

from api import db
from api.holding_snapshots import latest_snapshot
from api.migrate_resources import main, migrate_resources
from api.tasks import TaskRegistry
from src.agents import ips_storage, report_storage
from tests.test_authorization import seed


@pytest.fixture
def owners():
    with Session(db.engine) as session:
        _, clients = seed(session)
        session.commit()
    return clients


def write_ips(client_id=None, document_id="ips_legacy", **metadata):
    path = ips_storage.IPS_DIR / f"{document_id}.json"
    path.write_text(
        json.dumps(
            {
                "ips": {"client_name": "Same name"},
                "audit_trail": {},
                "metadata": {"client_id": client_id, "profile_id": 1, **metadata},
            }
        )
    )
    return path


def migrate(mappings=None):
    with db.engine.begin() as connection:
        return migrate_resources(connection, mappings)


def mapping(path, client_id, org="a"):
    return {
        "kind": "ips",
        "filename": path.name,
        "organization_id": org,
        "client_id": client_id,
    }


def test_stable_uuid_upgrade_is_idempotent_and_keeps_files(owners):
    path = write_ips(owners["own"])
    report = report_storage.save_report(
        "synthetic", "Same name", "fixture", client_id=owners["other"]
    )
    raw = path.read_bytes()
    with Session(db.engine) as session:
        session.add(
            db.TaskRecord(
                task_id="old",
                kind="ips",
                meta_json=json.dumps(
                    {
                        "organization_id": "a",
                        "client_id": owners["own"],
                        "created_by": "advisor",
                    }
                ),
                events_json='[{"type":"done","seq":1}]',
            )
        )
        session.add(
            db.HoldingSnapshotRecord(
                document_id=path.stem, as_of="2026-01-01", data={"sentinel": "kept"}
            )
        )
        session.commit()
    assert migrate() == {
        "artifacts": 2,
        "tasks": 1,
        "snapshots": 1,
        "unresolved_files": 0,
    }
    assert migrate() == {
        "artifacts": 0,
        "tasks": 0,
        "snapshots": 0,
        "unresolved_files": 0,
    }
    assert path.read_bytes() == raw
    with Session(db.engine) as session:
        artifact = session.get(db.ArtifactRecord, ("ips", path.stem))
        assert (artifact.organization_id, artifact.client_id, artifact.created_by) == (
            "a",
            owners["own"],
            None,
        )
        assert (
            session.get(db.ArtifactRecord, ("report", report.report_id)).client_id
            == owners["other"]
        )
        task = session.get(db.TaskRecord, "old")
        assert (task.organization_id, task.client_id, task.created_by) == (
            "a",
            owners["own"],
            "advisor",
        )
        assert task.events_json == '[{"type":"done","seq":1}]'
        assert (
            latest_snapshot(session, path.stem, organization_id="a")["sentinel"]
            == "kept"
        )
        assert latest_snapshot(session, path.stem, organization_id="b") is None


def test_ambiguous_or_conflicting_legacy_owners_stay_quarantined(owners):
    write_ips()
    write_ips("missing-client", "ips_missing")
    write_ips(owners["foreign"], "ips_conflict", organization_id="a")
    (ips_storage.IPS_DIR / "broken.json").write_text("not-json")
    with Session(db.engine) as session:
        for id_, meta in (
            ("legacy", {"profile_id": 1}),
            ("conflict", {"organization_id": "a", "client_id": owners["foreign"]}),
            ("unowned", {"organization_id": "a"}),
        ):
            session.add(
                db.TaskRecord(task_id=id_, kind="ips", meta_json=json.dumps(meta))
            )
        session.commit()
    assert migrate() == {
        "artifacts": 0,
        "tasks": 0,
        "snapshots": 0,
        "unresolved_files": 4,
    }
    with Session(db.engine) as session:
        assert session.get(db.TaskRecord, "conflict").organization_id is None


def test_cli_dry_run_and_explicit_adoption(owners, tmp_path, capsys):
    path = write_ips()
    raw = path.read_bytes()
    manifest = tmp_path / "mapping.json"
    manifest.write_text(json.dumps([mapping(path, owners["own"])]))
    assert main(["--mapping", str(manifest)]) == 0
    with Session(db.engine) as session:
        assert session.get(db.ArtifactRecord, ("ips", path.stem)) is None
    assert main(["--mapping", str(manifest), "--apply"]) == 0
    assert main(["--mapping", str(manifest), "--apply"]) == 0
    assert path.read_bytes() == raw
    with Session(db.engine) as session:
        assert (
            session.get(db.ArtifactRecord, ("ips", path.stem)).client_id
            == owners["own"]
        )
    output = capsys.readouterr().out
    assert owners["own"] not in output
    assert "Same name" not in output


def test_conflicting_mapping_rolls_back_whole_batch(owners):
    first = write_ips(None, "ips_first")
    second = write_ips(owners["foreign"], "ips_second")
    with pytest.raises(ValueError, match="conflicts"):
        migrate([mapping(first, owners["own"]), mapping(second, owners["own"])])
    with Session(db.engine) as session:
        assert session.get(db.ArtifactRecord, ("ips", first.stem)) is None


@pytest.mark.parametrize(
    "filename", ["../ips_legacy.json", "/tmp/ips_legacy.json", "missing.json"]
)
def test_mapping_refuses_unsafe_or_missing_files(owners, filename):
    with pytest.raises(ValueError):
        migrate(
            [
                {
                    "kind": "ips",
                    "filename": filename,
                    "organization_id": "a",
                    "client_id": owners["own"],
                }
            ]
        )


def test_migration_never_reassigns_existing_index(owners):
    path = write_ips()
    migrate([mapping(path, owners["own"])])
    with pytest.raises(ValueError, match="reassign"):
        migrate([mapping(path, owners["other"])])
    with Session(db.engine) as session:
        assert (
            session.get(db.ArtifactRecord, ("ips", path.stem)).client_id
            == owners["own"]
        )


def test_symlink_is_not_adopted(owners, tmp_path):
    external = tmp_path / "external.json"
    external.write_text(json.dumps({"metadata": {"client_id": owners["own"]}}))
    linked = ips_storage.IPS_DIR / "ips_link.json"
    linked.symlink_to(external)
    assert migrate()["artifacts"] == 0
    with pytest.raises(ValueError):
        migrate([mapping(linked, owners["own"])])


@pytest.mark.parametrize(
    "model,extra",
    [
        (
            db.ArtifactRecord,
            {"kind": "ips", "resource_id": "fixture", "filename": "fixture.json"},
        ),
        (db.TaskRecord, {"task_id": "fixture", "kind": "ips"}),
        (db.HoldingSnapshotRecord, {"document_id": "fixture", "as_of": "2026-01-01"}),
    ],
)
def test_database_rejects_cross_tenant_client_reference(owners, model, extra):
    with Session(db.engine) as session:
        session.add(model(organization_id="a", client_id=owners["foreign"], **extra))
        with pytest.raises(IntegrityError):
            session.commit()


def test_new_tasks_require_valid_durable_ownership(owners):
    registry = TaskRegistry()
    for meta in (
        {},
        {
            "organization_id": "a",
            "created_by": "advisor",
            "client_id": owners["foreign"],
        },
    ):
        with pytest.raises(RuntimeError, match="Unable to persist"):
            registry.create("ips", **meta)
    assert not registry._tasks
    task = registry.create("optimize", organization_id="a", created_by="advisor")
    with Session(db.engine) as session:
        row = session.get(db.TaskRecord, task.task_id)
        assert (row.organization_id, row.created_by, row.client_id) == (
            "a",
            "advisor",
            None,
        )


def legacy_resource_tables():
    with db.engine.begin() as connection:
        for table in ("background_tasks", "holding_snapshots", "app_settings"):
            connection.exec_driver_sql(f"DROP TABLE {table}")
        connection.exec_driver_sql(
            "CREATE TABLE background_tasks (task_id VARCHAR PRIMARY KEY, kind VARCHAR NOT NULL, status VARCHAR NOT NULL, meta_json VARCHAR NOT NULL, events_json VARCHAR NOT NULL, created_at VARCHAR NOT NULL, finished_at VARCHAR)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE holding_snapshots (id INTEGER PRIMARY KEY, document_id VARCHAR NOT NULL, as_of VARCHAR NOT NULL, created_at VARCHAR NOT NULL, data JSON)"
        )
        connection.exec_driver_sql(
            "CREATE TABLE app_settings (key VARCHAR PRIMARY KEY, value VARCHAR NOT NULL, updated_at VARCHAR NOT NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO background_tasks VALUES ('old','ips','completed','{}','[{\"type\":\"done\"}]','original',NULL)"
        )
        connection.exec_driver_sql(
            "INSERT INTO holding_snapshots VALUES (7,'unowned','2026-01-01','original','{\"original\": true}')"
        )
        connection.exec_driver_sql(
            "INSERT INTO app_settings VALUES ('test_setting','synthetic-value','original')"
        )


def test_schema_migration_preserves_rows_and_enforces_constraints(owners):
    legacy_resource_tables()
    db.init_db()
    db.init_db()
    with Session(db.engine) as session:
        assert session.get(db.TaskRecord, "old").events_json == '[{"type":"done"}]'
        assert session.get(db.HoldingSnapshotRecord, 7).data == {"original": True}
        setting = session.get(db.AppSettingRecord, "test_setting")
        assert (setting.scope, setting.value, setting.updated_at) == (
            "deployment",
            "synthetic-value",
            "original",
        )
        setting.scope = "organization"
        with pytest.raises(IntegrityError):
            session.commit()
    with db.engine.connect() as connection:
        assert not connection.exec_driver_sql("PRAGMA foreign_key_check").all()


def test_schema_migration_rolls_back_ddl_and_rows(owners):
    legacy_resource_tables()

    def fail_after_drop(
        connection, cursor, statement, parameters, context, executemany
    ):
        if statement == "ALTER TABLE background_tasks_owned RENAME TO background_tasks":
            raise RuntimeError("Injected failure")

    event.listen(db.engine, "before_cursor_execute", fail_after_drop)
    try:
        with pytest.raises(RuntimeError, match="Injected"):
            db.init_db()
    finally:
        event.remove(db.engine, "before_cursor_execute", fail_after_drop)
    with db.engine.connect() as connection:
        assert "organization_id" not in {
            c["name"] for c in inspect(connection).get_columns("background_tasks")
        }
        assert (
            connection.exec_driver_sql(
                "SELECT created_at FROM background_tasks"
            ).scalar()
            == "original"
        )
        assert "background_tasks_owned" not in inspect(connection).get_table_names()
    db.init_db()


@pytest.mark.parametrize(
    "meta",
    [
        "[]",
        "invalid",
        '{"organization_id":{}}',
        '{"organization_id":"a","client_id":["bad"],"created_by":"advisor"}',
    ],
)
def test_malformed_task_ownership_does_not_break_startup(owners, meta):
    with Session(db.engine) as session:
        session.add(db.TaskRecord(task_id="malformed", kind="ips", meta_json=meta))
        session.commit()
    db.init_db()
    with Session(db.engine) as session:
        assert session.get(db.TaskRecord, "malformed").organization_id is None


def test_schema_with_columns_but_without_constraints_is_rejected(owners):
    legacy_resource_tables()
    with db.engine.begin() as connection:
        for column in ("organization_id", "client_id", "created_by"):
            connection.exec_driver_sql(
                f"ALTER TABLE background_tasks ADD COLUMN {column} VARCHAR"
            )
    with pytest.raises(RuntimeError, match="Incompatible resource constraints"):
        db.init_db()


def test_cli_failure_is_redacted_and_rolls_back(owners, tmp_path, capsys):
    path = write_ips()
    manifest = tmp_path / "mapping.json"
    manifest.write_text(
        json.dumps([mapping(path, owners["own"]), mapping(path, owners["own"])])
    )
    assert main(["--mapping", str(manifest), "--apply"]) == 1
    with Session(db.engine) as session:
        assert session.get(db.ArtifactRecord, ("ips", path.stem)) is None
    output = capsys.readouterr().out
    assert owners["own"] not in output
    assert path.name not in output
