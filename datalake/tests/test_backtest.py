"""backtest.py のテスト"""
import sqlite3
import sys
import os

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.init_sqlite import init_sqlite
from scripts.migrate_phase14 import migrate


# ─────────────────────────────────────────────────────────────────────────────
# フィクスチャ
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    """Phase 14 スキーマ込みの SQLite ファイルパスを返す。"""
    path = str(tmp_path / "test.db")
    init_sqlite(path)
    migrate(path)
    return path


@pytest.fixture
def conn(db_path):
    c = sqlite3.connect(db_path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _seed(conn: sqlite3.Connection):
    """テスト用の最小データセットを投入する。"""
    # 銘柄マスタ
    conn.executemany(
        "INSERT OR REPLACE INTO stocks (code, name, sector) VALUES (?, ?, ?)",
        [
            ("7203", "トヨタ自動車", "輸送用機器"),
            ("6758", "ソニーグループ", "電気機器"),
        ],
    )

    # 取引日価格: 2024-01-04 〜 2024-01-15 (8営業日)
    prices = [
        ("7203", "2024-01-04", 3000.0, 3050.0, 2990.0, 3020.0, 5000000),
        ("7203", "2024-01-05", 3020.0, 3060.0, 3010.0, 3050.0, 4800000),
        ("7203", "2024-01-09", 3050.0, 3080.0, 3040.0, 3070.0, 5100000),
        ("7203", "2024-01-10", 3070.0, 3090.0, 3060.0, 3080.0, 4900000),
        ("7203", "2024-01-11", 3080.0, 3100.0, 3070.0, 3090.0, 5200000),
        ("7203", "2024-01-12", 3090.0, 3120.0, 3080.0, 3110.0, 4700000),
        ("7203", "2024-01-15", 3110.0, 3130.0, 3100.0, 3120.0, 4600000),
        ("6758", "2024-01-04", 2500.0, 2540.0, 2490.0, 2510.0, 3000000),
        ("6758", "2024-01-05", 2510.0, 2560.0, 2500.0, 2550.0, 2900000),
        ("6758", "2024-01-09", 2550.0, 2580.0, 2540.0, 2570.0, 3100000),
        ("6758", "2024-01-10", 2570.0, 2600.0, 2560.0, 2590.0, 2800000),
        ("6758", "2024-01-11", 2590.0, 2610.0, 2580.0, 2600.0, 3200000),
        ("6758", "2024-01-12", 2600.0, 2620.0, 2590.0, 2610.0, 2700000),
        ("6758", "2024-01-15", 2610.0, 2630.0, 2600.0, 2620.0, 2600000),
    ]
    conn.executemany(
        "INSERT OR REPLACE INTO daily_prices "
        "(code, date, open, high, low, close, volume) VALUES (?, ?, ?, ?, ?, ?, ?)",
        prices,
    )

    # シグナル: 2024-01-04 に bullish シグナル2件
    conn.executemany(
        "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        [
            ("2024-01-04", "causality_chain", "7203", None, "bullish", 0.8, "{}"),
            ("2024-01-04", "causality_chain", "6758", None, "bullish", 0.7, "{}"),
        ],
    )
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# _trading_days / _nth_trading_day_after
# ─────────────────────────────────────────────────────────────────────────────

class TestTradingDaysHelper:
    def test_returns_sorted_dates(self, conn):
        _seed(conn)
        from src.backtest.engine import _trading_days
        days = _trading_days(conn)
        assert days == sorted(days)
        assert "2024-01-04" in days

    def test_nth_after_existing_date(self, conn):
        _seed(conn)
        from src.backtest.engine import _trading_days, _nth_trading_day_after
        days = _trading_days(conn)
        result = _nth_trading_day_after(days, "2024-01-04", 1)
        assert result == "2024-01-05"

    def test_nth_after_non_trading_day(self, conn):
        """非取引日の場合 n=1 が翌取引日になる"""
        _seed(conn)
        from src.backtest.engine import _trading_days, _nth_trading_day_after
        days = _trading_days(conn)
        # 2024-01-06 は土曜で取引日なし → n=1 が翌取引日 01-09
        result = _nth_trading_day_after(days, "2024-01-06", 1)
        assert result == "2024-01-09"

    def test_returns_none_when_out_of_range(self, conn):
        _seed(conn)
        from src.backtest.engine import _trading_days, _nth_trading_day_after
        days = _trading_days(conn)
        result = _nth_trading_day_after(days, "2024-01-15", 1)
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# simulate_trades
# ─────────────────────────────────────────────────────────────────────────────

class TestSimulateTrades:
    def test_creates_trade_rows(self, conn, db_path):
        _seed(conn)
        from src.backtest.engine import simulate_trades

        # run_id を先に作る
        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('test', '2024-01-01', '2024-01-31', 5)"
        )
        conn.commit()
        run_id = cur.lastrowid

        trades = simulate_trades(conn, run_id, None, "2024-01-01", "2024-01-31", 5, None, 0.0)

        assert len(trades) == 2
        count = conn.execute(
            "SELECT COUNT(*) FROM backtest_trades WHERE run_id = ?", (run_id,)
        ).fetchone()[0]
        assert count == 2

    def test_entry_price_is_next_day_open(self, conn):
        _seed(conn)
        from src.backtest.engine import simulate_trades

        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('test', '2024-01-01', '2024-01-31', 5)"
        )
        conn.commit()
        run_id = cur.lastrowid

        trades = simulate_trades(conn, run_id, None, "2024-01-01", "2024-01-31", 5, None, 0.0)

        # シグナル発生日 2024-01-04 の翌取引日 01-05 の open = 3020
        toyota_trade = next(t for t in trades if t["code"] == "7203")
        assert toyota_trade["entry_date"] == "2024-01-05"
        assert toyota_trade["entry_price"] == 3020.0

    def test_return_rate_calculated_for_bullish(self, conn):
        _seed(conn)
        from src.backtest.engine import simulate_trades

        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('test', '2024-01-01', '2024-01-31', 3)"
        )
        conn.commit()
        run_id = cur.lastrowid

        trades = simulate_trades(conn, run_id, None, "2024-01-01", "2024-01-31", 3, None, 0.0)
        toyota_trade = next(t for t in trades if t["code"] == "7203")

        # entry 01-05 open=3020, exit = 3日後 01-10 close=3080
        # return = (3080 - 3020) / 3020 ≈ 0.01987
        assert toyota_trade["return_rate"] is not None
        assert toyota_trade["return_rate"] > 0

    def test_bearish_return_is_inverted(self, conn):
        """bearish シグナルのリターンは符号が反転する"""
        _seed(conn)
        from src.backtest.engine import simulate_trades

        # bearish シグナルを追加
        conn.execute(
            "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
            "VALUES ('2024-01-04', 'causality_chain', '7203', NULL, 'bearish', 0.8, '{}')"
        )
        conn.commit()

        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('test_bearish', '2024-01-01', '2024-01-31', 3)"
        )
        conn.commit()
        run_id = cur.lastrowid

        trades = simulate_trades(
            conn, run_id, None, "2024-01-01", "2024-01-31", 3, "bearish", 0.0
        )
        bearish_trade = next((t for t in trades if t["direction"] == "bearish"), None)
        assert bearish_trade is not None
        # 株価が上昇しているので bearish は負リターン (空売り損失)
        assert bearish_trade["return_rate"] < 0

    def test_min_confidence_filter(self, conn):
        """min_confidence より低い confidence のシグナルはスキップ"""
        _seed(conn)
        from src.backtest.engine import simulate_trades

        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('test', '2024-01-01', '2024-01-31', 5)"
        )
        conn.commit()
        run_id = cur.lastrowid

        # confidence 0.75 以上のみ → 7203(0.8) のみ, 6758(0.7) は除外
        trades = simulate_trades(conn, run_id, None, "2024-01-01", "2024-01-31", 5, None, 0.75)
        assert len(trades) == 1
        assert trades[0]["code"] == "7203"

    def test_no_trades_when_no_signals(self, conn):
        _seed(conn)
        from src.backtest.engine import simulate_trades

        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('test', '2024-01-01', '2024-01-31', 5)"
        )
        conn.commit()
        run_id = cur.lastrowid

        # シグナルが存在しない期間
        trades = simulate_trades(conn, run_id, None, "2023-01-01", "2023-01-31", 5, None, 0.0)
        assert len(trades) == 0


# ─────────────────────────────────────────────────────────────────────────────
# calc_metrics
# ─────────────────────────────────────────────────────────────────────────────

class TestCalcMetrics:
    def _insert_trades(self, conn, run_id, returns):
        for i, r in enumerate(returns):
            conn.execute(
                "INSERT INTO backtest_trades "
                "(run_id, signal_id, code, signal_date, direction, return_rate) "
                "VALUES (?, ?, '7203', '2024-01-04', 'bullish', ?)",
                (run_id, i + 1, r),
            )
        conn.commit()

    def test_win_rate(self, conn):
        from src.backtest.engine import calc_metrics

        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('m', '2024-01-01', '2024-01-31', 5)"
        )
        conn.commit()
        run_id = cur.lastrowid

        # 3勝1敗 → 75%
        self._insert_trades(conn, run_id, [0.02, 0.03, -0.01, 0.01])
        result = calc_metrics(conn, run_id)

        assert result["total_trades"] == 4
        assert result["winning_trades"] == 3
        assert abs(result["win_rate"] - 0.75) < 1e-6

    def test_avg_return(self, conn):
        from src.backtest.engine import calc_metrics

        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('m', '2024-01-01', '2024-01-31', 5)"
        )
        conn.commit()
        run_id = cur.lastrowid

        self._insert_trades(conn, run_id, [0.04, -0.02])
        result = calc_metrics(conn, run_id)

        assert abs(result["avg_return"] - 0.01) < 1e-6

    def test_max_drawdown(self, conn):
        from src.backtest.engine import calc_metrics, _calc_max_drawdown

        # 手動検証
        returns = [0.05, 0.03, -0.08, 0.02]
        # 累積: 0.05, 0.08, 0.00, 0.02
        # peak: 0.05, 0.08, 0.08, 0.08
        # dd:   0,    0,    0.08, 0.06 → max = 0.08
        dd = _calc_max_drawdown(returns)
        assert abs(dd - 0.08) < 1e-6

    def test_sharpe_ratio_none_for_single_trade(self, conn):
        from src.backtest.engine import _calc_sharpe
        assert _calc_sharpe([0.02]) is None

    def test_empty_trades_returns_zeros(self, conn):
        from src.backtest.engine import calc_metrics

        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('m', '2024-01-01', '2024-01-31', 5)"
        )
        conn.commit()
        run_id = cur.lastrowid

        result = calc_metrics(conn, run_id)

        assert result["total_trades"] == 0
        assert result["win_rate"] == 0.0
        assert result["avg_return"] == 0.0

    def test_result_saved_to_db(self, conn):
        from src.backtest.engine import calc_metrics

        cur = conn.execute(
            "INSERT INTO backtest_runs (name, from_date, to_date, holding_days) "
            "VALUES ('m', '2024-01-01', '2024-01-31', 5)"
        )
        conn.commit()
        run_id = cur.lastrowid

        self._insert_trades(conn, run_id, [0.01, 0.02])
        calc_metrics(conn, run_id)

        row = conn.execute(
            "SELECT run_id FROM backtest_results WHERE run_id = ?", (run_id,)
        ).fetchone()
        assert row is not None


# ─────────────────────────────────────────────────────────────────────────────
# run_backtest (統合テスト)
# ─────────────────────────────────────────────────────────────────────────────

class TestRunBacktest:
    def test_end_to_end(self, db_path):
        """シード → run_backtest → DB に結果が保存される"""
        conn = sqlite3.connect(db_path)
        _seed(conn)
        conn.close()

        from src.backtest.engine import run_backtest
        result = run_backtest(
            db_path=db_path,
            name="E2Eテスト",
            from_date="2024-01-01",
            to_date="2024-01-31",
            holding_days=5,
        )

        assert "run_id" in result
        assert result["run_id"] >= 1
        m = result["metrics"]
        assert m["total_trades"] == 2
        assert 0.0 <= m["win_rate"] <= 1.0

    def test_signal_type_filter(self, db_path):
        """signal_type フィルタが機能する"""
        conn = sqlite3.connect(db_path)
        _seed(conn)
        # fund_flow シグナルを追加
        conn.execute(
            "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
            "VALUES ('2024-01-04', 'fund_flow', '7203', NULL, 'bullish', 0.8, '{}')"
        )
        conn.commit()
        conn.close()

        from src.backtest.engine import run_backtest
        result = run_backtest(
            db_path=db_path,
            name="fund_flow only",
            from_date="2024-01-01",
            to_date="2024-01-31",
            holding_days=3,
            signal_type="fund_flow",
        )
        assert result["metrics"]["total_trades"] == 1

    def test_run_saved_to_db(self, db_path):
        """実行設定が backtest_runs テーブルに保存される"""
        conn = sqlite3.connect(db_path)
        _seed(conn)
        conn.close()

        from src.backtest.engine import run_backtest
        result = run_backtest(
            db_path=db_path,
            name="保存確認",
            from_date="2024-01-01",
            to_date="2024-01-31",
            holding_days=5,
        )

        conn = sqlite3.connect(db_path)
        row = conn.execute(
            "SELECT name, holding_days FROM backtest_runs WHERE id = ?",
            (result["run_id"],),
        ).fetchone()
        conn.close()

        assert row is not None
        assert row[0] == "保存確認"
        assert row[1] == 5
