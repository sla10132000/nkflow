"""api/helpers.py のユニットテスト。"""
import sqlite3

import pytest
from fastapi import HTTPException

from src.api.helpers import period_sql_expr, require_stock, safe_json_loads


# ── require_stock ─────────────────────────────────────────────────────

class TestRequireStock:
    @pytest.fixture
    def conn(self, tmp_path):
        db = tmp_path / "test.db"
        c = sqlite3.connect(str(db))
        c.row_factory = sqlite3.Row
        c.execute("CREATE TABLE stocks (code TEXT PRIMARY KEY, name TEXT, sector TEXT)")
        c.execute("INSERT INTO stocks VALUES ('7203', 'トヨタ', '輸送用機器')")
        c.commit()
        return c

    def test_returns_stock_dict(self, conn):
        result = require_stock(conn, "7203")
        assert result["code"] == "7203"
        assert result["name"] == "トヨタ"
        assert result["sector"] == "輸送用機器"

    def test_raises_404_for_missing_stock(self, conn):
        with pytest.raises(HTTPException) as exc:
            require_stock(conn, "9999")
        assert exc.value.status_code == 404
        assert "9999" in exc.value.detail


# ── safe_json_loads ───────────────────────────────────────────────────

class TestSafeJsonLoads:
    def test_parses_valid_json(self):
        assert safe_json_loads('{"a": 1}') == {"a": 1}

    def test_returns_default_for_none(self):
        assert safe_json_loads(None) is None

    def test_returns_custom_default_for_none(self):
        assert safe_json_loads(None, default=[]) == []

    def test_returns_default_for_invalid_json(self):
        assert safe_json_loads("not-json") is None

    def test_returns_default_for_invalid_type(self):
        assert safe_json_loads(12345, default="fallback") == "fallback"

    def test_parses_json_list(self):
        assert safe_json_loads('[1, 2, 3]') == [1, 2, 3]


# ── period_sql_expr ───────────────────────────────────────────────────

class TestPeriodSqlExpr:
    def test_week(self):
        assert period_sql_expr("week") == "strftime('%Y-W%W', date)"

    def test_month(self):
        assert period_sql_expr("month") == "strftime('%Y-%m', date)"

    def test_invalid_raises_400(self):
        with pytest.raises(HTTPException) as exc:
            period_sql_expr("day")
        assert exc.value.status_code == 400
        assert "day" in exc.value.detail
