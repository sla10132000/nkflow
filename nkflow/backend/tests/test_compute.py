"""compute.py のテスト (fixtures/sample_prices.csv 使用)"""
import os
import sqlite3
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")
SAMPLE_CSV = os.path.join(FIXTURES_DIR, "sample_prices.csv")

STOCKS = [
    ("7203", "トヨタ自動車", "輸送用機器"),
    ("6758", "ソニーグループ", "電気機器"),
    ("6902", "デンソー", "輸送用機器"),
]


@pytest.fixture
def db_path(tmp_path):
    """スキーマ初期化 + サンプルデータ挿入済みの SQLite パス"""
    path = str(tmp_path / "test.db")
    init_sqlite(path)

    conn = sqlite3.connect(path)
    conn.executemany("INSERT INTO stocks VALUES (?, ?, ?)", STOCKS)

    df = pd.read_csv(SAMPLE_CSV)
    df["code"] = df["code"].astype(str).str.zfill(4)
    rows = [
        (r.code, r.date, r.open, r.high, r.low, r.close, int(r.volume),
         None, None, None, None)
        for r in df.itertuples(index=False)
    ]
    conn.executemany(
        "INSERT INTO daily_prices "
        "(code, date, open, high, low, close, volume, "
        " return_rate, price_range, range_pct, relative_strength) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    conn.close()
    return path


# ── compute_returns ──────────────────────────────────────────────────────────

class TestComputeReturns:
    def test_return_rate_calculation(self, db_path):
        """騰落率 = (close - prev_close) / prev_close"""
        from src.batch.compute import compute_returns

        compute_returns(db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT date, close, return_rate FROM daily_prices "
            "WHERE code = '7203' ORDER BY date"
        ).fetchall()
        conn.close()

        # 先頭日は return_rate が NULL
        assert rows[0][2] is None

        # 2日目以降は (close - prev_close) / prev_close に一致
        for i in range(1, len(rows)):
            _, close, rr = rows[i]
            prev_close = rows[i - 1][1]
            expected = (close - prev_close) / prev_close
            assert abs(rr - expected) < 1e-9

    def test_price_range_calculation(self, db_path):
        """値幅 = high - low"""
        from src.batch.compute import compute_returns

        compute_returns(db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT high, low, price_range FROM daily_prices "
            "WHERE code = '7203' AND price_range IS NOT NULL"
        ).fetchall()
        conn.close()

        assert len(rows) > 0
        for high, low, pr in rows:
            assert abs(pr - (high - low)) < 1e-6

    def test_range_pct_calculation(self, db_path):
        """値幅率 = (high - low) / open"""
        from src.batch.compute import compute_returns

        compute_returns(db_path)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT open, high, low, range_pct FROM daily_prices "
            "WHERE code = '7203' AND range_pct IS NOT NULL"
        ).fetchall()
        conn.close()

        assert len(rows) > 0
        for open_, high, low, rp in rows:
            expected = (high - low) / open_
            assert abs(rp - expected) < 1e-9

    def test_first_day_is_null(self, db_path):
        """各銘柄の最初の日は前日データがないため NULL"""
        from src.batch.compute import compute_returns

        compute_returns(db_path)

        conn = sqlite3.connect(db_path)
        for code, _, _ in STOCKS:
            first_date = conn.execute(
                "SELECT MIN(date) FROM daily_prices WHERE code = ?", (code,)
            ).fetchone()[0]
            rr = conn.execute(
                "SELECT return_rate FROM daily_prices WHERE code = ? AND date = ?",
                (code, first_date),
            ).fetchone()[0]
            assert rr is None, f"code={code} の初日 return_rate は NULL のはず"
        conn.close()

    def test_target_date_filter(self, db_path):
        """target_date を指定すると、その日だけ更新される"""
        from src.batch.compute import compute_returns

        conn = sqlite3.connect(db_path)
        dates = conn.execute(
            "SELECT DISTINCT date FROM daily_prices ORDER BY date"
        ).fetchall()
        conn.close()

        target = dates[5][0]  # 6日目
        updated = compute_returns(db_path, target_date=target)

        conn = sqlite3.connect(db_path)
        # 対象日は全銘柄更新済み
        non_null = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date = ? AND return_rate IS NOT NULL",
            (target,),
        ).fetchone()[0]
        # 対象日以外は NULL のまま
        other_null = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date != ? AND return_rate IS NOT NULL",
            (target,),
        ).fetchone()[0]
        conn.close()

        assert non_null == len(STOCKS)
        assert other_null == 0
        assert updated == len(STOCKS)

    def test_returns_row_count(self, db_path):
        """全計算時の更新行数は (全行数 - 銘柄数) = 各銘柄の先頭日を除く"""
        from src.batch.compute import compute_returns

        conn = sqlite3.connect(db_path)
        total_rows = conn.execute("SELECT COUNT(*) FROM daily_prices").fetchone()[0]
        conn.close()

        updated = compute_returns(db_path)
        assert updated == total_rows - len(STOCKS)


# ── compute_relative_strength ─────────────────────────────────────────────────

class TestComputeRelativeStrength:
    def _seed_returns(self, db_path):
        from src.batch.compute import compute_returns
        compute_returns(db_path)

    def test_relative_strength_with_summary(self, db_path):
        """daily_summary に nikkei_return がある場合はそれを使う"""
        self._seed_returns(db_path)
        from src.batch.compute import compute_relative_strength

        conn = sqlite3.connect(db_path)
        target_date = conn.execute(
            "SELECT MIN(date) FROM daily_prices WHERE return_rate IS NOT NULL"
        ).fetchone()[0]

        nikkei_return = 0.005
        conn.execute(
            "INSERT INTO daily_summary (date, nikkei_return) VALUES (?, ?)",
            (target_date, nikkei_return),
        )
        conn.commit()
        conn.close()

        compute_relative_strength(db_path, target_date)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT return_rate, relative_strength FROM daily_prices "
            "WHERE date = ? AND return_rate IS NOT NULL",
            (target_date,),
        ).fetchall()
        conn.close()

        for rr, rs in rows:
            assert abs(rs - (rr - nikkei_return)) < 1e-9

    def test_relative_strength_fallback_to_average(self, db_path):
        """daily_summary がない場合は全銘柄平均で代替"""
        self._seed_returns(db_path)
        from src.batch.compute import compute_relative_strength

        conn = sqlite3.connect(db_path)
        target_date = conn.execute(
            "SELECT MIN(date) FROM daily_prices WHERE return_rate IS NOT NULL"
        ).fetchone()[0]
        conn.close()

        compute_relative_strength(db_path, target_date)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT return_rate, relative_strength FROM daily_prices "
            "WHERE date = ? AND return_rate IS NOT NULL",
            (target_date,),
        ).fetchall()
        conn.close()

        # 全銘柄の rs 合計はほぼ 0 (各リターンから平均を引くため)
        rs_sum = sum(rs for _, rs in rows)
        assert abs(rs_sum) < 1e-6

    def test_null_return_rate_skipped(self, db_path):
        """return_rate が NULL の行は relative_strength も NULL のまま"""
        from src.batch.compute import compute_relative_strength

        conn = sqlite3.connect(db_path)
        first_date = conn.execute(
            "SELECT MIN(date) FROM daily_prices"
        ).fetchone()[0]
        conn.close()

        # 騰落率を計算しないまま relative_strength を実行
        compute_relative_strength(db_path, first_date)

        conn = sqlite3.connect(db_path)
        rs_count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices WHERE date = ? AND relative_strength IS NOT NULL",
            (first_date,),
        ).fetchone()[0]
        conn.close()

        assert rs_count == 0


# ── compute_correlations ──────────────────────────────────────────────────────

class TestComputeCorrelations:
    def _seed_returns(self, db_path):
        from src.batch.compute import compute_returns
        compute_returns(db_path)

    def test_saves_high_correlation_pairs(self, db_path):
        """|coeff| >= CORRELATION_THRESHOLD のペアが保存される"""
        self._seed_returns(db_path)
        from src.batch.compute import compute_correlations

        conn = sqlite3.connect(db_path)
        calc_date = conn.execute(
            "SELECT MAX(date) FROM daily_prices"
        ).fetchone()[0]
        conn.close()

        compute_correlations(db_path, calc_date)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT stock_a, stock_b, coefficient FROM graph_correlations"
        ).fetchall()
        conn.close()

        # 保存済みペアの係数は全て閾値以上
        from src.config import CORRELATION_THRESHOLD
        for _, _, coef in rows:
            assert abs(coef) >= CORRELATION_THRESHOLD

    def test_stock_a_lt_stock_b(self, db_path):
        """stock_a < stock_b の順序が保証される"""
        self._seed_returns(db_path)
        from src.batch.compute import compute_correlations

        conn = sqlite3.connect(db_path)
        calc_date = conn.execute("SELECT MAX(date) FROM daily_prices").fetchone()[0]
        conn.close()

        compute_correlations(db_path, calc_date)

        conn = sqlite3.connect(db_path)
        rows = conn.execute(
            "SELECT stock_a, stock_b FROM graph_correlations"
        ).fetchall()
        conn.close()

        for a, b in rows:
            assert a < b, f"stock_a ({a}) は stock_b ({b}) より小さいはず"

    def test_period_label_stored(self, tmp_path):
        """period カラムに '20d' 等の文字列が保存される (高相関データで検証)"""
        import numpy as np

        db_path = str(tmp_path / "corr.db")
        init_sqlite(db_path)

        conn = sqlite3.connect(db_path)
        conn.executemany("INSERT INTO stocks VALUES (?,?,?)", STOCKS[:2])

        # 7203 と 6758 のリターンをほぼ同一にして相関係数 ≈ 1.0 を保証
        np.random.seed(0)
        base_returns = np.random.normal(0.001, 0.015, 25)
        rows = []
        for i, ret in enumerate(base_returns):
            d = f"2024-11-{i+1:02d}" if i < 9 else f"2024-11-{i+1}"
            # 日付を連番で作る (営業日判定は不要)
            from datetime import date, timedelta
            d = (date(2024, 11, 1) + timedelta(days=i)).isoformat()
            for code, ret_noise in [("7203", 0.0), ("6758", 0.0001)]:
                r = ret + ret_noise
                rows.append((code, d, 1000.0, 1010.0, 990.0, round(1000 * (1 + r), 2),
                              1000000, r, 20.0, 0.02, None))
        conn.executemany(
            "INSERT INTO daily_prices "
            "(code, date, open, high, low, close, volume, "
            " return_rate, price_range, range_pct, relative_strength) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            rows,
        )
        conn.commit()
        conn.close()

        from src.batch.compute import compute_correlations
        calc_date = rows[-1][1]
        compute_correlations(db_path, calc_date)

        conn = sqlite3.connect(db_path)
        periods = conn.execute(
            "SELECT DISTINCT period FROM graph_correlations"
        ).fetchall()
        conn.close()

        stored_periods = {p[0] for p in periods}
        assert "20d" in stored_periods

    def test_insufficient_data_skips_gracefully(self, tmp_path):
        """データが 2 日分しかない場合でもエラーにならない"""
        db_path = str(tmp_path / "tiny.db")
        init_sqlite(db_path)

        conn = sqlite3.connect(db_path)
        conn.executemany("INSERT INTO stocks VALUES (?,?,?)", STOCKS[:2])
        conn.executemany(
            "INSERT INTO daily_prices "
            "(code, date, open, high, low, close, volume, "
            " return_rate, price_range, range_pct, relative_strength) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [
                ("7203", "2025-01-06", 100, 105, 98, 102, 1000, None, None, None, None),
                ("7203", "2025-01-07", 102, 107, 100, 104, 1100, 0.02, 7.0, 0.07, None),
            ],
        )
        conn.commit()
        conn.close()

        from src.batch.compute import compute_correlations
        # 銘柄が 1 つしかないため相関は計算不可 → エラーなく 0 を返す
        result = compute_correlations(db_path, "2025-01-07")
        assert result == 0


# ── compute_sector_summary ────────────────────────────────────────────────────

class TestComputeSectorSummary:
    def test_saves_sector_rotation_json(self, db_path):
        """セクター別集計が daily_summary の sector_rotation に JSON で保存される"""
        from src.batch.compute import compute_returns, compute_sector_summary
        import json

        compute_returns(db_path)

        conn = sqlite3.connect(db_path)
        target_date = conn.execute(
            "SELECT MIN(date) FROM daily_prices WHERE return_rate IS NOT NULL"
        ).fetchone()[0]
        conn.close()

        compute_sector_summary(db_path, target_date)

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT sector_rotation FROM daily_summary WHERE date = ?", (target_date,)
        ).fetchone()
        conn.close()

        assert row is not None
        data = json.loads(row[0])
        assert isinstance(data, list)
        assert len(data) > 0
        assert "sector" in data[0]
        assert "avg_return" in data[0]


# ── compute_all ───────────────────────────────────────────────────────────────

class TestComputeAll:
    def test_all_columns_populated(self, db_path):
        """compute_all 後に return_rate / relative_strength が埋まっている"""
        from src.batch.compute import compute_all

        conn = sqlite3.connect(db_path)
        target_date = conn.execute(
            "SELECT MAX(date) FROM daily_prices"
        ).fetchone()[0]
        conn.close()

        compute_all(db_path, target_date)

        conn = sqlite3.connect(db_path)
        null_count = conn.execute(
            "SELECT COUNT(*) FROM daily_prices "
            "WHERE date = ? AND return_rate IS NULL",
            (target_date,),
        ).fetchone()[0]
        conn.close()

        assert null_count == 0
