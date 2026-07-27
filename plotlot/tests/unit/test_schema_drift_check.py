"""Tests for the startup schema-drift check.

Regression guard for the failure that broke harness persistence: a model gained
a column, create_all silently left the existing table alone, and every write
against that table 500'd at runtime with no warning anywhere.

Uses SQLite in-memory so it runs anywhere (no Postgres required).
"""

from sqlalchemy import Column, Integer, MetaData, String, Table, create_engine

from plotlot.storage.db import _detect_schema_drift
from plotlot.storage.models import Base


def _drift_against(create_sql: list[str], monkeypatch, tables: dict) -> list[str]:
    """Build a throwaway SQLite DB, point Base.metadata at `tables`, return drift."""
    engine = create_engine("sqlite://")
    with engine.begin() as conn:
        for stmt in create_sql:
            conn.exec_driver_sql(stmt)
        monkeypatch.setattr(Base.metadata, "tables", tables)
        return _detect_schema_drift(conn)


def test_reports_missing_column(monkeypatch):
    """The real-world case: table exists but the model has a newer column."""
    md = MetaData()
    model = Table("widgets", md, Column("id", Integer, primary_key=True), Column("owner", String))
    drift = _drift_against(
        ["CREATE TABLE widgets (id INTEGER PRIMARY KEY)"],  # no `owner`
        monkeypatch,
        {"widgets": model},
    )
    assert len(drift) == 1
    assert "widgets missing columns: owner" in drift[0]


def test_reports_missing_table(monkeypatch):
    md = MetaData()
    model = Table("ghosts", md, Column("id", Integer, primary_key=True))
    drift = _drift_against([], monkeypatch, {"ghosts": model})
    assert drift == ["missing table: ghosts"]


def test_clean_schema_reports_nothing(monkeypatch):
    md = MetaData()
    model = Table("widgets", md, Column("id", Integer, primary_key=True), Column("owner", String))
    drift = _drift_against(
        ["CREATE TABLE widgets (id INTEGER PRIMARY KEY, owner VARCHAR)"],
        monkeypatch,
        {"widgets": model},
    )
    assert drift == []


def test_extra_db_columns_and_tables_are_ignored(monkeypatch):
    """This DB is shared with MLflow — never flag tables/columns we don't own."""
    md = MetaData()
    model = Table("widgets", md, Column("id", Integer, primary_key=True))
    drift = _drift_against(
        [
            "CREATE TABLE widgets (id INTEGER PRIMARY KEY, legacy_col VARCHAR)",
            "CREATE TABLE mlflow_runs (id INTEGER PRIMARY KEY)",
        ],
        monkeypatch,
        {"widgets": model},
    )
    assert drift == []
