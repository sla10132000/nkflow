"""batch/db.py のユニットテスト。"""
import sqlite3

import pytest

from src.batch.db import duckdb_sqlite


class TestDuckdbSqlite:
    @pytest.fixture
    def db_path(self, tmp_path):
        db = tmp_path / "test.db"
        conn = sqlite3.connect(str(db))
        conn.execute("CREATE TABLE t (id INTEGER, val TEXT)")
        conn.execute("INSERT INTO t VALUES (1, 'a'), (2, 'b')")
        conn.commit()
        conn.close()
        return str(db)

    def test_reads_sqlite_data(self, db_path):
        with duckdb_sqlite(db_path) as duck:
            df = duck.execute("SELECT * FROM sq.t ORDER BY id").df()
        assert len(df) == 2
        assert list(df["val"]) == ["a", "b"]

    def test_connection_closed_after_exit(self, db_path):
        with duckdb_sqlite(db_path) as duck:
            pass
        # DuckDB connection should be closed — calling execute should raise
        with pytest.raises(Exception):
            duck.execute("SELECT 1")

    def test_connection_closed_on_exception(self, db_path):
        with pytest.raises(ValueError):
            with duckdb_sqlite(db_path) as duck:
                raise ValueError("test error")
        with pytest.raises(Exception):
            duck.execute("SELECT 1")

    def test_custom_alias(self, db_path):
        with duckdb_sqlite(db_path, alias="mydb") as duck:
            df = duck.execute("SELECT * FROM mydb.t").df()
        assert len(df) == 2
