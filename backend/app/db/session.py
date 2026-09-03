from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine, event, inspect, text
from sqlalchemy.exc import SQLAlchemyError


REQUIRED_TABLES = {
    "accessibility_routes",
    "accessibility_segments",
    "hazards",
    "hazard_observations",
    "hazard_status_history",
}


def sqlite_url(database_path: Path) -> str:
    return f"sqlite+pysqlite:///{database_path.resolve().as_posix()}"


def create_database_engine(database_path: Path) -> Engine:
    database_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        sqlite_url(database_path),
        connect_args={"check_same_thread": False},
        pool_pre_ping=True,
    )

    @event.listens_for(engine, "connect")
    def enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


def check_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    missing = REQUIRED_TABLES - set(inspect(engine).get_table_names())
    if missing:
        raise SQLAlchemyError(
            f"Local database schema is missing required tables: {sorted(missing)}"
        )
