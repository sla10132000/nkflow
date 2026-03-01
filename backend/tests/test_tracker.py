"""
Phase 11: tracker.py のテスト

- evaluate_pending_signals: 未評価シグナルの判定
- aggregate_accuracy: タイプ別集計
- run_all: 統合実行
"""
import sqlite3
import tempfile
import os
import pytest

from src.batch.tracker import (
    evaluate_pending_signals,
    aggregate_accuracy,
    run_all,
    _judge,
    _cumulative_return,
    _nth_trading_date,
    HIT_THRESHOLD,
)
from scripts.init_sqlite import init_sqlite


# ─────────────────────────────────────────────────────────────────────────────
# フィクスチャ
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_path(tmp_path):
    """初期化済み SQLite のパスを返す。"""
    path = str(tmp_path / "test.db")
    init_sqlite(path)
    return path


@pytest.fixture
def db_with_data(db_path):
    """
    25 取引日分の価格データ + シグナルを挿入したDBを返す。
    銘柄: A001, A002
    取引日: 2024-01-01 〜 2024-02-09 (25営業日相当)
    """
    conn = sqlite3.connect(db_path)

    conn.execute("INSERT INTO stocks (code, name, sector) VALUES ('A001', 'Alpha', 'Tech')")
    conn.execute("INSERT INTO stocks (code, name, sector) VALUES ('A002', 'Beta',  'Finance')")

    # 25 取引日のダミーデータを生成 (return_rate は +1% 固定)
    dates = _make_trading_dates("2024-01-04", 25)
    for d in dates:
        for code in ("A001", "A002"):
            conn.execute(
                "INSERT INTO daily_prices (code, date, open, high, low, close, volume, return_rate) "
                "VALUES (?, ?, 100, 101, 99, 100, 10000, 0.01)",
                (code, d),
            )

    # シグナル: 初日 (2024-01-04) に bullish シグナル (A001)
    conn.execute(
        "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
        "VALUES ('2024-01-04', 'causality_chain', 'A001', NULL, 'bullish', 0.8, '{}')"
    )
    # シグナル: 初日 (2024-01-04) に bearish シグナル (A002) — 実際は上昇するので miss
    conn.execute(
        "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
        "VALUES ('2024-01-04', 'fund_flow', 'A002', 'Finance', 'bearish', 0.7, '{}')"
    )
    # code が NULL のシグナル (評価対象外)
    conn.execute(
        "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
        "VALUES ('2024-01-04', 'regime_shift', NULL, 'Tech', 'bullish', 0.6, '{}')"
    )

    conn.commit()
    conn.close()
    return db_path


def _make_trading_dates(start: str, n: int) -> list[str]:
    """start から n 取引日(月〜金)の日付リストを返す。"""
    from datetime import date, timedelta
    d = date.fromisoformat(start)
    result = []
    while len(result) < n:
        if d.weekday() < 5:  # 月〜金
            result.append(d.isoformat())
        d += timedelta(days=1)
    return result


# ─────────────────────────────────────────────────────────────────────────────
# ユーティリティテスト
# ─────────────────────────────────────────────────────────────────────────────

class TestJudge:
    def test_bullish_hit(self):
        assert _judge("bullish", 0.01) == "hit"

    def test_bullish_miss(self):
        assert _judge("bullish", -0.01) == "miss"

    def test_bullish_tie(self):
        assert _judge("bullish", 0.0) == "tie"

    def test_bearish_hit(self):
        assert _judge("bearish", -0.01) == "hit"

    def test_bearish_miss(self):
        assert _judge("bearish", 0.01) == "miss"

    def test_bearish_threshold_boundary(self):
        # 境界値: HIT_THRESHOLD ちょうどは tie
        assert _judge("bullish", HIT_THRESHOLD) == "tie"
        assert _judge("bullish", HIT_THRESHOLD + 1e-9) == "hit"


class TestNthTradingDate:
    def test_returns_nth_date(self, db_with_data):
        conn = sqlite3.connect(db_with_data)
        try:
            dates = _make_trading_dates("2024-01-04", 25)
            result = _nth_trading_date(conn, "2024-01-04", 5)
            # "2024-01-04" の翌取引日から数えて5番目
            # dates[0]=2024-01-04 なので、その翌日起算で5番目 = dates[5]
            assert result == dates[5]
        finally:
            conn.close()

    def test_returns_none_when_insufficient(self, db_with_data):
        conn = sqlite3.connect(db_with_data)
        try:
            # データが 25 日分しかないので 100 日目は取得不可
            result = _nth_trading_date(conn, "2024-01-04", 100)
            assert result is None
        finally:
            conn.close()


class TestCumulativeReturn:
    def test_sums_returns(self, db_with_data):
        conn = sqlite3.connect(db_with_data)
        try:
            # 全日 return_rate=0.01 なので 5 日累積 = 0.05
            result = _cumulative_return(conn, "A001", "2024-01-04", 5)
            assert result == pytest.approx(0.05)
        finally:
            conn.close()

    def test_returns_none_when_insufficient(self, db_with_data):
        conn = sqlite3.connect(db_with_data)
        try:
            result = _cumulative_return(conn, "A001", "2024-01-04", 100)
            assert result is None
        finally:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# evaluate_pending_signals テスト
# ─────────────────────────────────────────────────────────────────────────────

class TestEvaluatePendingSignals:
    def test_records_results_for_completed_horizons(self, db_with_data):
        # 2024-01-04 シグナルを 25 日後 (十分な期間) で評価
        trading_dates = _make_trading_dates("2024-01-04", 25)
        eval_date = trading_dates[-1]  # 最終取引日

        n = evaluate_pending_signals(db_with_data, eval_date)
        assert n > 0

        conn = sqlite3.connect(db_with_data)
        try:
            rows = conn.execute("SELECT * FROM signal_results").fetchall()
            assert len(rows) > 0
        finally:
            conn.close()

    def test_bullish_hit(self, db_with_data):
        """return_rate=+1% 固定なので bullish はすべて hit になる。"""
        trading_dates = _make_trading_dates("2024-01-04", 25)
        eval_date = trading_dates[-1]
        evaluate_pending_signals(db_with_data, eval_date)

        conn = sqlite3.connect(db_with_data)
        try:
            # A001 (bullish) の 5 日ホライズン
            row = conn.execute(
                """
                SELECT sr.result FROM signal_results sr
                JOIN signals s ON sr.signal_id = s.id
                WHERE s.code = 'A001' AND sr.horizon_days = 5
                """
            ).fetchone()
            assert row is not None
            assert row[0] == "hit"
        finally:
            conn.close()

    def test_bearish_miss(self, db_with_data):
        """return_rate=+1% 固定なので bearish はすべて miss になる。"""
        trading_dates = _make_trading_dates("2024-01-04", 25)
        eval_date = trading_dates[-1]
        evaluate_pending_signals(db_with_data, eval_date)

        conn = sqlite3.connect(db_with_data)
        try:
            row = conn.execute(
                """
                SELECT sr.result FROM signal_results sr
                JOIN signals s ON sr.signal_id = s.id
                WHERE s.code = 'A002' AND sr.horizon_days = 5
                """
            ).fetchone()
            assert row is not None
            assert row[0] == "miss"
        finally:
            conn.close()

    def test_null_code_signals_skipped(self, db_with_data):
        """code が NULL のシグナルは評価対象外。"""
        trading_dates = _make_trading_dates("2024-01-04", 25)
        eval_date = trading_dates[-1]
        evaluate_pending_signals(db_with_data, eval_date)

        conn = sqlite3.connect(db_with_data)
        try:
            # regime_shift (code=NULL) は signal_results に記録されない
            null_sig_id = conn.execute(
                "SELECT id FROM signals WHERE code IS NULL"
            ).fetchone()[0]
            row = conn.execute(
                "SELECT 1 FROM signal_results WHERE signal_id = ?", (null_sig_id,)
            ).fetchone()
            assert row is None
        finally:
            conn.close()

    def test_idempotent(self, db_with_data):
        """2回実行しても重複記録しない。"""
        trading_dates = _make_trading_dates("2024-01-04", 25)
        eval_date = trading_dates[-1]
        evaluate_pending_signals(db_with_data, eval_date)
        evaluate_pending_signals(db_with_data, eval_date)

        conn = sqlite3.connect(db_with_data)
        try:
            # PRIMARY KEY (signal_id, horizon_days) で重複不可なので件数が倍にならない
            count = conn.execute("SELECT COUNT(*) FROM signal_results").fetchone()[0]
            # A001 + A002 の 3 ホライズン = 6 件のみ (code=NULL は除外)
            assert count == 6
        finally:
            conn.close()

    def test_early_eval_skips_incomplete_horizons(self, db_with_data):
        """評価期限に達していないシグナルはスキップされる。"""
        # 2024-01-04 シグナルを翌日(1取引日後)で評価 → horizon=5,10,20 はすべてスキップ
        n = evaluate_pending_signals(db_with_data, "2024-01-05")
        assert n == 0


# ─────────────────────────────────────────────────────────────────────────────
# aggregate_accuracy テスト
# ─────────────────────────────────────────────────────────────────────────────

class TestAggregateAccuracy:
    def test_aggregates_correctly(self, db_with_data):
        trading_dates = _make_trading_dates("2024-01-04", 25)
        eval_date = trading_dates[-1]
        evaluate_pending_signals(db_with_data, eval_date)
        aggregate_accuracy(db_with_data, eval_date)

        conn = sqlite3.connect(db_with_data)
        try:
            rows = conn.execute("SELECT * FROM signal_accuracy").fetchall()
            assert len(rows) > 0

            # causality_chain は hit_rate=1.0 のはず (bullish, 全日上昇)
            cc_row = conn.execute(
                "SELECT hit_rate FROM signal_accuracy "
                "WHERE signal_type='causality_chain' AND horizon_days=5"
            ).fetchone()
            if cc_row:
                assert cc_row[0] == pytest.approx(1.0)
        finally:
            conn.close()

    def test_upsert_on_same_date(self, db_with_data):
        """同じ calc_date で 2 回 aggregate しても行が重複しない。"""
        trading_dates = _make_trading_dates("2024-01-04", 25)
        eval_date = trading_dates[-1]
        evaluate_pending_signals(db_with_data, eval_date)
        aggregate_accuracy(db_with_data, eval_date)
        aggregate_accuracy(db_with_data, eval_date)

        conn = sqlite3.connect(db_with_data)
        try:
            count = conn.execute(
                "SELECT COUNT(*) FROM signal_accuracy WHERE calc_date=?", (eval_date,)
            ).fetchone()[0]
            # (causality_chain + fund_flow) × 3 horizons = 6 行
            assert count == 6
        finally:
            conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# run_all テスト
# ─────────────────────────────────────────────────────────────────────────────

class TestRunAll:
    def test_run_all_integration(self, db_with_data):
        trading_dates = _make_trading_dates("2024-01-04", 25)
        eval_date = trading_dates[-1]
        n = run_all(db_with_data, eval_date)

        assert n > 0

        conn = sqlite3.connect(db_with_data)
        try:
            assert conn.execute("SELECT COUNT(*) FROM signal_results").fetchone()[0] > 0
            assert conn.execute("SELECT COUNT(*) FROM signal_accuracy").fetchone()[0] > 0
        finally:
            conn.close()
