"""Resource ownership upgrade and explicit legacy-artifact adoption.

Startup indexes only stable Client UUIDs already written by #75. Ambiguous files
and tasks remain quarantined. The CLI accepts an operator-reviewed mapping; it
never uses client names, numeric profile IDs, or profile file paths as ownership.
All SQL changes are committed atomically; artifact payload files are not edited.
"""

import argparse
import json
from pathlib import Path

from sqlalchemy import Connection, MetaData, inspect, select
from sqlalchemy.schema import CheckConstraint, CreateTable

from api import db


def migrate_resource_schema(connection: Connection) -> None:
    additions = {
        db.TaskRecord: {"organization_id", "client_id", "created_by"},
        db.HoldingSnapshotRecord: {"organization_id", "client_id", "created_by"},
        db.AppSettingRecord: {"scope"},
    }
    for model, new_columns in additions.items():
        table = model.__table__
        columns = {c["name"] for c in inspect(connection).get_columns(table.name)}
        expected = set(table.columns.keys())
        if columns == expected:
            inspector = inspect(connection)
            actual_fks = {
                (
                    tuple(fk["constrained_columns"]),
                    fk["referred_table"],
                    tuple(fk["referred_columns"]),
                )
                for fk in inspector.get_foreign_keys(table.name)
            }
            expected_fks = {
                (
                    tuple(fk.column_keys),
                    fk.referred_table.name,
                    tuple(element.column.name for element in fk.elements),
                )
                for fk in table.foreign_key_constraints
            }
            actual_checks = {
                "".join(c["sqltext"].lower().split())
                for c in inspector.get_check_constraints(table.name)
            }
            expected_checks = {
                "".join(str(c.sqltext).lower().split())
                for c in table.constraints
                if isinstance(c, CheckConstraint)
            }
            if not expected_fks <= actual_fks or not expected_checks <= actual_checks:
                raise RuntimeError(
                    "Incompatible resource constraints; migration aborted"
                )
            for index in table.indexes:
                index.create(connection, checkfirst=True)
            continue
        if columns != expected - new_columns:
            raise RuntimeError("Unrecognized resource schema; migration aborted")
        metadata = MetaData()
        for parent in (db.OrganizationRecord, db.UserRecord, db.ClientRecord):
            parent.__table__.to_metadata(metadata)
        replacement = table.to_metadata(metadata, name=table.name + "_owned")
        connection.execute(CreateTable(replacement))
        names = ", ".join(sorted(columns))
        extra_names, extra_values = (
            (", scope", ", 'deployment'") if model is db.AppSettingRecord else ("", "")
        )
        connection.exec_driver_sql(
            f"INSERT INTO {replacement.name} ({names}{extra_names}) "
            f"SELECT {names}{extra_values} FROM {table.name}"
        )
        connection.exec_driver_sql(f"DROP TABLE {table.name}")
        connection.exec_driver_sql(
            f"ALTER TABLE {replacement.name} RENAME TO {table.name}"
        )
        for index in table.indexes:
            index.create(connection)


def _owner(connection, client_id, organization_id=None):
    if not isinstance(client_id, str) or not client_id:
        return None
    row = (
        connection.execute(
            select(db.ClientRecord.__table__).where(db.ClientRecord.id == client_id)
        )
        .mappings()
        .first()
    )
    if row is None or (
        organization_id is not None and row["organization_id"] != organization_id
    ):
        return None
    return row["organization_id"], row["id"]


def _creator(connection, user_id):
    if not isinstance(user_id, str) or not user_id:
        return None
    return connection.execute(
        select(db.UserRecord.id).where(db.UserRecord.id == user_id)
    ).scalar_one_or_none()


def migrate_resources(
    connection: Connection, mappings: list[dict] | None = None
) -> dict[str, int]:
    from src.agents import ips_storage, report_storage

    explicit = {}
    for mapping in mappings or []:
        if not isinstance(mapping, dict) or set(mapping) != {
            "kind",
            "filename",
            "organization_id",
            "client_id",
        }:
            raise ValueError(
                "Mapping requires kind, filename, organization_id and client_id"
            )
        kind, filename = mapping["kind"], mapping["filename"]
        if (
            kind not in ("ips", "report")
            or not isinstance(filename, str)
            or Path(filename).name != filename
            or not filename.endswith(".json")
        ):
            raise ValueError("Invalid artifact mapping")
        if (
            not isinstance(mapping["organization_id"], str)
            or not mapping["organization_id"]
        ):
            raise ValueError("Invalid organization")
        if (kind, filename) in explicit or not _owner(
            connection, mapping["client_id"], mapping["organization_id"]
        ):
            raise ValueError("Duplicate mapping or invalid owner")
        explicit[kind, filename] = mapping

    counts = {"artifacts": 0, "tasks": 0, "snapshots": 0, "unresolved_files": 0}
    seen = set()
    scanned_ids: dict[tuple[str, str], tuple[str, bool]] = {}
    for kind, directory in (
        ("ips", ips_storage.IPS_DIR),
        ("report", report_storage.REPORTS_DIR),
    ):
        for path in sorted(directory.glob("*.json")):
            key = kind, path.name
            mapping = explicit.get(key)
            try:
                if path.is_symlink():
                    raise ValueError("Symlink")
                data = json.loads(path.read_text(encoding="utf-8"))
                meta = data["metadata"] if kind == "ips" else data
                resource_id = path.stem if kind == "ips" else data["report_id"]
                if (
                    not isinstance(meta, dict)
                    or not isinstance(resource_id, str)
                    or not resource_id
                ):
                    raise ValueError("Invalid artifact")
                if kind == "ips" and not all(
                    c.isalnum() or c in "_-" for c in resource_id
                ):
                    raise ValueError("Invalid ID")
                if kind == "report" and not resource_id.replace("_", "").isdigit():
                    raise ValueError("Invalid ID")
            except (OSError, ValueError, TypeError, KeyError):
                if mapping:
                    raise ValueError("Mapped artifact is unreadable") from None
                counts["unresolved_files"] += 1
                continue
            seen.add(key)
            old = (
                connection.execute(
                    select(db.ArtifactRecord.__table__).where(
                        db.ArtifactRecord.kind == kind,
                        db.ArtifactRecord.resource_id == resource_id,
                    )
                )
                .mappings()
                .first()
            )
            identity = kind, resource_id
            previous = scanned_ids.get(identity)
            if previous is not None and previous[0] != path.name and not previous[1]:
                # No authoritative index existed before this scan. Never let file
                # ordering pick one owner from ambiguous legacy copies.
                raise ValueError("Duplicate legacy artifact ID; migration aborted")
            scanned_ids.setdefault(identity, (path.name, old is not None))
            if mapping:
                client_id, organization_id = (
                    mapping["client_id"],
                    mapping["organization_id"],
                )
                if meta.get("client_id") not in (None, "", client_id) or meta.get(
                    "organization_id"
                ) not in (None, "", organization_id):
                    raise ValueError("Mapping conflicts with stored ownership")
                owner = (organization_id, client_id)
            else:
                owner = _owner(
                    connection, meta.get("client_id"), meta.get("organization_id")
                )
            if old:
                if mapping and (
                    old["organization_id"],
                    old["client_id"],
                    old["filename"],
                ) != (*owner, path.name):
                    raise ValueError("Mapping cannot reassign an indexed artifact")
                if (
                    old["filename"] != path.name
                    or meta.get("client_id") not in (None, "", old["client_id"])
                    or meta.get("organization_id")
                    not in (None, "", old["organization_id"])
                ):
                    counts["unresolved_files"] += 1
                continue
            if owner is None:
                counts["unresolved_files"] += 1
                continue
            connection.execute(
                db.ArtifactRecord.__table__.insert().values(
                    kind=kind,
                    resource_id=resource_id,
                    filename=path.name,
                    organization_id=owner[0],
                    client_id=owner[1],
                    created_by=_creator(connection, meta.get("created_by")),
                )
            )
            counts["artifacts"] += 1
    if set(explicit) - seen:
        raise ValueError("Mapped artifact not found")

    for row in connection.execute(
        select(db.TaskRecord.__table__).where(db.TaskRecord.organization_id.is_(None))
    ).mappings():
        try:
            meta = json.loads(row["meta_json"])
            if not isinstance(meta, dict):
                continue
        except (ValueError, TypeError):
            continue
        org = meta.get("organization_id")
        if not isinstance(org, str) or not org:
            continue
        if meta.get("client_id") not in (None, "") and not isinstance(
            meta["client_id"], str
        ):
            continue
        creator = _creator(connection, meta.get("created_by"))
        owner = _owner(connection, meta.get("client_id"), org) if org else None
        if meta.get("client_id") and owner is None:
            continue
        if (
            not org
            or not connection.execute(
                select(db.OrganizationRecord.id).where(db.OrganizationRecord.id == org)
            ).first()
        ):
            continue
        if owner is None and creator is None:
            continue
        connection.execute(
            db.TaskRecord.__table__.update()
            .where(db.TaskRecord.task_id == row["task_id"])
            .values(
                organization_id=org,
                client_id=owner[1] if owner else None,
                created_by=creator,
            )
        )
        counts["tasks"] += 1

    for row in connection.execute(
        select(db.HoldingSnapshotRecord.__table__).where(
            db.HoldingSnapshotRecord.organization_id.is_(None)
        )
    ).mappings():
        artifact = (
            connection.execute(
                select(db.ArtifactRecord.__table__).where(
                    db.ArtifactRecord.kind == "ips",
                    db.ArtifactRecord.resource_id == row["document_id"],
                )
            )
            .mappings()
            .first()
        )
        if artifact:
            connection.execute(
                db.HoldingSnapshotRecord.__table__.update()
                .where(db.HoldingSnapshotRecord.id == row["id"])
                .values(
                    organization_id=artifact["organization_id"],
                    client_id=artifact["client_id"],
                )
            )
            counts["snapshots"] += 1
    return counts


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate/index resource ownership; dry-run unless --apply"
    )
    parser.add_argument(
        "--mapping", type=Path, help="JSON array of explicit legacy artifact owners"
    )
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    try:
        mappings = (
            json.loads(args.mapping.read_text(encoding="utf-8")) if args.mapping else []
        )
        if not isinstance(mappings, list):
            raise ValueError("Mapping must be an array")
        with db.engine.connect() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            try:
                from api.migrate_ownership import migrate_ownership

                db.SQLModel.metadata.create_all(connection)
                db.CLIENT_ORGANIZATION_INDEX.create(connection, checkfirst=True)
                migrate_ownership(connection)
                migrate_resource_schema(connection)
                counts = migrate_resources(connection, mappings)
                if args.apply:
                    connection.commit()
                else:
                    connection.rollback()
            except Exception:
                connection.rollback()
                raise
    except Exception:
        print(
            "Resource migration failed; no changes committed. Check schema and ownership mapping."
        )
        return 1
    print(json.dumps({"applied": args.apply, **counts}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
