"""Transactional upgrade of the pre-#73 SQLite profile table.

Called under init_db's BEGIN IMMEDIATE transaction. Keep IDs, timestamps,
raw JSON and the reserved user_id unchanged; never infer login permissions.
"""

from uuid import uuid4

from sqlalchemy import Connection, MetaData, inspect, text
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.schema import CreateTable

from api.db import ClientRecord, OrganizationRecord, ProfileRecord
from api.ownership import LOCAL_ORGANIZATION_ID, LOCAL_ORGANIZATION_NAME


def migrate_ownership(connection: Connection) -> None:
    columns = {
        column["name"] for column in inspect(connection).get_columns("client_profiles")
    }
    if "client_id" in columns:
        return
    expected = {column.name for column in ProfileRecord.__table__.columns} - {
        "client_id"
    }
    if columns != expected:
        raise RuntimeError("Unrecognized legacy profile schema; migration aborted")

    # A separate table is needed to enforce NOT NULL, UNIQUE and FOREIGN KEY
    # on existing SQLite rows. Do not rename the old table or deserialize JSON.
    table = ProfileRecord.__table__.to_metadata(
        MetaData(), name="client_profiles_owned"
    )
    # Make the referenced table available to SQLAlchemy's DDL compiler.
    ClientRecord.__table__.to_metadata(table.metadata)
    connection.execute(CreateTable(table))
    profile_ids = (
        connection.execute(text("SELECT id FROM client_profiles ORDER BY id"))
        .scalars()
        .all()
    )
    if profile_ids:
        connection.execute(
            insert(OrganizationRecord)
            .values(id=LOCAL_ORGANIZATION_ID, name=LOCAL_ORGANIZATION_NAME)
            .on_conflict_do_nothing(index_elements=["id"])
        )
    for profile_id in profile_ids:
        client_id = str(uuid4())
        connection.execute(
            insert(ClientRecord).values(
                id=client_id, organization_id=LOCAL_ORGANIZATION_ID, user_id=None
            )
        )
        connection.execute(
            text(
                "INSERT INTO client_profiles_owned "
                "(id, client_id, user_id, name, age, risk_level, created_at, updated_at, data) "
                "SELECT id, :client_id, user_id, name, age, risk_level, created_at, updated_at, data "
                "FROM client_profiles WHERE id = :profile_id"
            ),
            {"client_id": client_id, "profile_id": profile_id},
        )
    connection.exec_driver_sql("DROP TABLE client_profiles")
    connection.exec_driver_sql(
        "ALTER TABLE client_profiles_owned RENAME TO client_profiles"
    )
    for index in ProfileRecord.__table__.indexes:
        index.create(connection)
    if connection.exec_driver_sql("PRAGMA foreign_key_check(client_profiles)").first():
        raise RuntimeError("Profile ownership migration failed integrity check")
