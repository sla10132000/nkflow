"""予測シグナル生成モジュール"""
import json
import logging
import sqlite3
from collections import defaultdict
from datetime import date
from typing import Any, Optional

logger = logging.getLogger(__name__)

# シグナル生成のしきい値
TRIGGER_RETURN_THRESHOLD = 0.02   # causality_chain 起点の最小騰落率 (絶対値)
CLUSTER_DEVIATION_THRESHOLD = 0.01  # cluster_breakout の最小乖離幅

# Phase 13: 信用残・為替シグナルのしきい値
MARGIN_RATIO_HIGH = 8.0           # 信用倍率がこれ以上 → 追証リスク高
MARGIN_RATIO_DANGER = 15.0        # 信用倍率がこれ以上 → 高リスク
FX_CHANGE_THRESHOLD = 0.005       # 為替変動率がこれ以上 → シグナル対象 (0.5%)

# 円安受益セクター (セクター名の部分一致で判定)
YEN_WEAK_BENEFIT_SECTORS = ["輸送用機器", "機械", "電気機器", "精密機器", "ガラス・土石製品"]
# 円高受益セクター
YEN_STRONG_BENEFIT_SECTORS = ["空運業", "陸運業", "小売業", "食料品", "水産・農林業"]


# ─────────────────────────────────────────────────────────────────────────────
# 1. causality_chain
# ─────────────────────────────────────────────────────────────────────────────

def generate_causality_chain_signals(
    conn: sqlite3.Connection,
    target_date: str,
    chains: list[dict[str, Any]],
) -> int:
    """
    因果連鎖シグナルを生成する。

    当日 |return_rate| > TRIGGER_RETURN_THRESHOLD の銘柄を起点に、
    GRANGER_CAUSES チェーンで繋がる follower 銘柄への追随シグナルを生成する。

    confidence = 1 - p_value (graph_causality から取得)

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'
        chains: graph.query_causality_chains() の戻り値
    Returns:
        生成したシグナル数
    """
    # 当日大きく動いたトリガー銘柄を取得
    trigger_rows = conn.execute(
        """
        SELECT dp.code, dp.return_rate, s.name
        FROM daily_prices dp
        JOIN stocks s ON dp.code = s.code
        WHERE dp.date = ? AND ABS(dp.return_rate) > ?
        """,
        (target_date, TRIGGER_RETURN_THRESHOLD),
    ).fetchall()

    if not trigger_rows:
        return 0

    trigger_map = {row[0]: {"return_rate": row[1], "name": row[2]} for row in trigger_rows}

    signals = []
    seen = set()  # (leader, follower) 重複排除

    for chain in chains:
        leader = chain["leader"]
        follower = chain["follower"]
        lag_total = int(chain.get("lag_total", 1))

        if leader not in trigger_map:
            continue
        if (leader, follower) in seen:
            continue
        seen.add((leader, follower))

        trigger_info = trigger_map[leader]

        # graph_causality から最小 p_value を取得
        row = conn.execute(
            "SELECT MIN(p_value) FROM graph_causality "
            "WHERE source = ? AND target = ? AND calc_date = ?",
            (leader, follower, target_date),
        ).fetchone()
        p_value = float(row[0]) if row and row[0] is not None else 0.05
        confidence = round(min(1.0, 1.0 - p_value), 4)

        direction = "bullish" if trigger_info["return_rate"] > 0 else "bearish"
        reasoning = json.dumps(
            {
                "trigger": {
                    "code": leader,
                    "name": trigger_info["name"],
                    "return": round(trigger_info["return_rate"], 4),
                },
                "chain": f"{leader}→{follower}",
                "lag_days": lag_total,
            },
            ensure_ascii=False,
        )
        signals.append(
            (target_date, "causality_chain", follower, None, direction, confidence, reasoning)
        )

    if signals:
        conn.executemany(
            "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            signals,
        )
        conn.commit()

    logger.info(f"causality_chain シグナル: {len(signals)} 件")
    return len(signals)


# ─────────────────────────────────────────────────────────────────────────────
# 2. fund_flow
# ─────────────────────────────────────────────────────────────────────────────

def generate_fund_flow_signals(
    conn: sqlite3.Connection,
    target_date: str,
) -> int:
    """
    資金フローシグナルを生成する。

    graph_fund_flows で inflow として記録されたセクターの全銘柄を bullish シグナル化する。
    confidence = 過去90日で同 sector_to への inflow 発生回数 / 90

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'
    Returns:
        生成したシグナル数
    """
    ff_rows = conn.execute(
        "SELECT sector_from, sector_to, return_spread FROM graph_fund_flows WHERE date = ?",
        (target_date,),
    ).fetchall()

    if not ff_rows:
        return 0

    signals = []
    for sector_from, sector_to, return_spread in ff_rows:
        # 過去90日の同パターン発生回数
        past_count = conn.execute(
            "SELECT COUNT(*) FROM graph_fund_flows "
            "WHERE sector_to = ? AND date < ? AND date >= date(?, '-90 days')",
            (sector_to, target_date, target_date),
        ).fetchone()[0]
        confidence = round(min(1.0, (past_count + 1) / 90), 4)

        stocks = conn.execute(
            "SELECT code FROM stocks WHERE sector = ?", (sector_to,)
        ).fetchall()

        for (code,) in stocks:
            reasoning = json.dumps(
                {
                    "sector_from": sector_from,
                    "sector_to": sector_to,
                    "return_spread": round(float(return_spread or 0), 4),
                    "past_occurrences": past_count,
                },
                ensure_ascii=False,
            )
            signals.append(
                (target_date, "fund_flow", code, sector_to, "bullish", confidence, reasoning)
            )

    if signals:
        conn.executemany(
            "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            signals,
        )
        conn.commit()

    logger.info(f"fund_flow シグナル: {len(signals)} 件")
    return len(signals)


# ─────────────────────────────────────────────────────────────────────────────
# 3. regime_shift
# ─────────────────────────────────────────────────────────────────────────────

def generate_regime_shift_signals(
    conn: sqlite3.Connection,
    target_date: str,
    regime_perf: dict[str, list[dict]],
) -> int:
    """
    レジーム変化シグナルを生成する。

    前日→当日でレジームが変化した場合、新レジームで過去に
    アウトパフォームした上位銘柄に対してシグナルを生成する。

    confidence = 0.5 + abs(avg_relative_strength) * 10 (上限 1.0)

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'
        regime_perf: graph.query_regime_performance() の戻り値
    Returns:
        生成したシグナル数
    """
    today_row = conn.execute(
        "SELECT regime FROM daily_summary WHERE date = ?", (target_date,)
    ).fetchone()
    if not today_row or not today_row[0]:
        return 0
    today_regime = today_row[0]

    prev_row = conn.execute(
        "SELECT regime FROM daily_summary WHERE date < ? ORDER BY date DESC LIMIT 1",
        (target_date,),
    ).fetchone()
    if not prev_row or prev_row[0] == today_regime:
        return 0  # レジーム変化なし

    prev_regime = prev_row[0]
    top_stocks = regime_perf.get(today_regime, [])
    if not top_stocks:
        return 0

    direction = "bullish" if today_regime == "risk_on" else "bearish"

    signals = []
    for item in top_stocks[:10]:
        code = item.get("code")
        avg_rs = float(item.get("avg_rs") or 0)
        if not code:
            continue

        confidence = round(min(1.0, 0.5 + abs(avg_rs) * 10), 4)
        reasoning = json.dumps(
            {
                "regime_from": prev_regime,
                "regime_to": today_regime,
                "avg_relative_strength": round(avg_rs, 4),
            },
            ensure_ascii=False,
        )
        signals.append(
            (target_date, "regime_shift", code, None, direction, confidence, reasoning)
        )

    if signals:
        conn.executemany(
            "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            signals,
        )
        conn.commit()

    logger.info(f"regime_shift シグナル: {len(signals)} 件 ({prev_regime} → {today_regime})")
    return len(signals)


# ─────────────────────────────────────────────────────────────────────────────
# 4. cluster_breakout
# ─────────────────────────────────────────────────────────────────────────────

def generate_cluster_breakout_signals(
    conn: sqlite3.Connection,
    target_date: str,
) -> int:
    """
    クラスター内乖離シグナルを生成する。

    同じコミュニティ内で他銘柄の平均と逆方向に動いた銘柄に対して
    平均回帰を期待したシグナルを生成する。

    - コミュニティ平均 > 0 かつ 個別 return < 平均 - threshold → bullish (反発期待)
    - コミュニティ平均 < 0 かつ 個別 return > 平均 + threshold → bearish (反落期待)

    confidence = min(1.0, |deviation| * 10)

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'
    Returns:
        生成したシグナル数
    """
    rows = conn.execute(
        """
        SELECT gc.code, gc.community_id, dp.return_rate, s.sector
        FROM graph_communities gc
        JOIN daily_prices dp ON gc.code = dp.code AND dp.date = ?
        JOIN stocks s ON gc.code = s.code
        WHERE gc.calc_date = ? AND dp.return_rate IS NOT NULL
        """,
        (target_date, target_date),
    ).fetchall()

    if not rows:
        return 0

    # コミュニティ別にリターンを集計
    by_community: dict[int, list[tuple[str, float, str]]] = defaultdict(list)
    for code, community_id, return_rate, sector in rows:
        by_community[community_id].append((code, float(return_rate), sector))

    signals = []
    for community_id, members in by_community.items():
        if len(members) < 2:
            continue

        avg_return = sum(r for _, r, _ in members) / len(members)

        for code, return_rate, sector in members:
            deviation = return_rate - avg_return

            if abs(deviation) < CLUSTER_DEVIATION_THRESHOLD:
                continue

            # 平均回帰シグナル:
            # コミュニティが上昇基調なのに個別が下落 → bullish
            if avg_return > 0 and deviation < -CLUSTER_DEVIATION_THRESHOLD:
                direction = "bullish"
            # コミュニティが下落基調なのに個別が上昇 → bearish
            elif avg_return < 0 and deviation > CLUSTER_DEVIATION_THRESHOLD:
                direction = "bearish"
            else:
                continue

            confidence = round(min(1.0, abs(deviation) * 10), 4)
            reasoning = json.dumps(
                {
                    "community_id": community_id,
                    "community_avg_return": round(avg_return, 4),
                    "stock_return": round(return_rate, 4),
                    "deviation": round(deviation, 4),
                },
                ensure_ascii=False,
            )
            signals.append(
                (target_date, "cluster_breakout", code, sector, direction, confidence, reasoning)
            )

    if signals:
        conn.executemany(
            "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            signals,
        )
        conn.commit()

    logger.info(f"cluster_breakout シグナル: {len(signals)} 件")
    return len(signals)


# ─────────────────────────────────────────────────────────────────────────────
# 5. margin_squeeze (Phase 13)
# ─────────────────────────────────────────────────────────────────────────────

def generate_margin_squeeze_signals(
    conn: sqlite3.Connection,
    target_date: str,
) -> int:
    """
    信用追証リスクシグナルを生成する。

    信用倍率が高い (買い残が売り残を大きく上回る) 銘柄が当日下落した場合、
    追証による強制売りの連鎖が起きやすい → bearish シグナル。

    confidence:
      ratio >= MARGIN_RATIO_DANGER: 0.8 + return_factor
      ratio >= MARGIN_RATIO_HIGH:   0.5 + return_factor
      return_factor = min(0.2, abs(return_rate) * 4)

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'
    Returns:
        生成したシグナル数
    """
    # 最新の信用残高データがある週を取得
    latest_week = conn.execute(
        "SELECT MAX(week_date) FROM margin_balances WHERE week_date <= ?",
        (target_date,),
    ).fetchone()[0]

    if not latest_week:
        logger.info("margin_squeeze: 信用残高データなし — スキップ")
        return 0

    # 信用倍率が高く当日下落した銘柄を抽出
    rows = conn.execute(
        """
        SELECT mb.code, mb.margin_ratio, mb.margin_buy, mb.margin_sell,
               dp.return_rate, s.name
        FROM margin_balances mb
        JOIN daily_prices dp ON mb.code = dp.code AND dp.date = ?
        JOIN stocks s ON mb.code = s.code
        WHERE mb.week_date = ?
          AND mb.margin_ratio >= ?
          AND dp.return_rate < -0.01
        ORDER BY mb.margin_ratio DESC
        """,
        (target_date, latest_week, MARGIN_RATIO_HIGH),
    ).fetchall()

    if not rows:
        return 0

    signals = []
    for code, margin_ratio, margin_buy, margin_sell, return_rate, name in rows:
        return_factor = min(0.2, abs(float(return_rate)) * 4)
        if float(margin_ratio) >= MARGIN_RATIO_DANGER:
            base_conf = 0.8
        else:
            base_conf = 0.5
        confidence = round(min(1.0, base_conf + return_factor), 4)

        reasoning = json.dumps(
            {
                "margin_ratio": round(float(margin_ratio), 2),
                "margin_buy": float(margin_buy) if margin_buy else None,
                "margin_sell": float(margin_sell) if margin_sell else None,
                "return_rate": round(float(return_rate), 4),
                "week_date": latest_week,
            },
            ensure_ascii=False,
        )
        signals.append(
            (target_date, "margin_squeeze", code, None, "bearish", confidence, reasoning)
        )

    if signals:
        conn.executemany(
            "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            signals,
        )
        conn.commit()

    logger.info(f"margin_squeeze シグナル: {len(signals)} 件")
    return len(signals)


# ─────────────────────────────────────────────────────────────────────────────
# 6. yen_sensitivity (Phase 13)
# ─────────────────────────────────────────────────────────────────────────────

def generate_yen_sensitivity_signals(
    conn: sqlite3.Connection,
    target_date: str,
) -> int:
    """
    為替感応度シグナルを生成する。

    当日 USDJPY の変動率が FX_CHANGE_THRESHOLD を超えた場合、
    セクター別の受益方向でシグナルを生成する。

    - 円安 (USDJPY 上昇): YEN_WEAK_BENEFIT_SECTORS → bullish
    - 円高 (USDJPY 下落): YEN_STRONG_BENEFIT_SECTORS → bullish

    confidence = min(1.0, abs(change_rate) * 40)

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'
    Returns:
        生成したシグナル数
    """
    row = conn.execute(
        "SELECT change_rate, close FROM exchange_rates WHERE date = ? AND pair = 'USDJPY'",
        (target_date,),
    ).fetchone()

    if not row or row[0] is None:
        logger.info("yen_sensitivity: 当日 USDJPY データなし — スキップ")
        return 0

    change_rate, usdjpy_close = float(row[0]), float(row[1])

    if abs(change_rate) < FX_CHANGE_THRESHOLD:
        logger.info(f"yen_sensitivity: 変動率 {change_rate:.4f} < 閾値 — スキップ")
        return 0

    yen_weakening = change_rate > 0  # True=円安, False=円高
    target_sectors = YEN_WEAK_BENEFIT_SECTORS if yen_weakening else YEN_STRONG_BENEFIT_SECTORS
    direction = "bullish"  # 受益セクターに対して常に bullish

    confidence = round(min(1.0, abs(change_rate) * 40), 4)
    fx_label = f"円安 ({change_rate:+.2%})" if yen_weakening else f"円高 ({change_rate:+.2%})"

    signals = []
    for sector_keyword in target_sectors:
        # セクター名の部分一致で銘柄を抽出
        stock_rows = conn.execute(
            "SELECT code FROM stocks WHERE sector LIKE ?",
            (f"%{sector_keyword}%",),
        ).fetchall()

        for (code,) in stock_rows:
            reasoning = json.dumps(
                {
                    "fx_event": fx_label,
                    "usdjpy": round(usdjpy_close, 2),
                    "change_rate": round(change_rate, 4),
                    "benefit_type": "yen_weak" if yen_weakening else "yen_strong",
                    "sector_keyword": sector_keyword,
                },
                ensure_ascii=False,
            )
            signals.append(
                (target_date, "yen_sensitivity", code, sector_keyword, direction, confidence, reasoning)
            )

    if signals:
        conn.executemany(
            "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            signals,
        )
        conn.commit()

    logger.info(f"yen_sensitivity シグナル: {len(signals)} 件 ({fx_label})")
    return len(signals)


# ─────────────────────────────────────────────────────────────────────────────
# 7. credit_overheating (Phase 16)
# ─────────────────────────────────────────────────────────────────────────────

# 信用過熱シグナルのしきい値
CREDIT_PL_RATIO_THRESHOLD = 0.12    # 評価損益率がこれ以上
CREDIT_BUY_GROWTH_THRESHOLD = 0.08  # 信用買残4週増加率がこれ以上


def generate_credit_overheating_signal(
    conn: sqlite3.Connection,
    target_date: str,
) -> int:
    """
    信用過熱警報シグナルを生成する。

    発動条件: pl_ratio > 0.12 AND buy_growth_4w > 0.08
    direction: 'bearish' (天井圏警告)
    confidence: 0.5 + min(0.4, (pl_ratio - 0.12) * 4 + (buy_growth_4w - 0.08) * 2)

    発動時: market_pressure_daily.signal_flags を {"credit_overheating": true} に更新する。

    Args:
        conn: SQLite 接続
        target_date: 'YYYY-MM-DD'
    Returns:
        生成したシグナル数 (0 または 1)
    """
    row = conn.execute(
        """
        SELECT pl_ratio, buy_growth_4w, pl_zone
        FROM market_pressure_daily
        WHERE date = ?
        """,
        (target_date,),
    ).fetchone()

    if not row or row[0] is None or row[1] is None:
        logger.info("credit_overheating: market_pressure_daily データなし — スキップ")
        return 0

    pl_ratio = float(row[0])
    buy_growth_4w = float(row[1])
    pl_zone = row[2] or "neutral"

    if pl_ratio <= CREDIT_PL_RATIO_THRESHOLD or buy_growth_4w <= CREDIT_BUY_GROWTH_THRESHOLD:
        logger.info(
            f"credit_overheating: 条件未達 (pl_ratio={pl_ratio:.3f}, buy_growth_4w={buy_growth_4w:.3f})"
        )
        return 0

    confidence = round(
        min(1.0, 0.5 + min(0.4, (pl_ratio - CREDIT_PL_RATIO_THRESHOLD) * 4
                               + (buy_growth_4w - CREDIT_BUY_GROWTH_THRESHOLD) * 2)),
        4,
    )

    reasoning = json.dumps(
        {
            "pl_ratio": round(pl_ratio, 4),
            "buy_growth_4w": round(buy_growth_4w, 4),
            "pl_zone": pl_zone,
            "condition": "credit_overheating",
        },
        ensure_ascii=False,
    )

    conn.execute(
        "INSERT INTO signals (date, signal_type, code, sector, direction, confidence, reasoning) "
        "VALUES (?, 'credit_overheating', NULL, NULL, 'bearish', ?, ?)",
        (target_date, confidence, reasoning),
    )

    # signal_flags を更新
    conn.execute(
        """
        UPDATE market_pressure_daily
        SET signal_flags = ?
        WHERE date = ?
        """,
        (json.dumps({"credit_overheating": True}), target_date),
    )

    conn.commit()
    logger.info(
        f"credit_overheating シグナル: 発動 (confidence={confidence}, pl_zone={pl_zone})"
    )
    return 1


# ─────────────────────────────────────────────────────────────────────────────
# daily_summary 更新
# ─────────────────────────────────────────────────────────────────────────────

def update_daily_summary(conn: sqlite3.Connection, target_date: str) -> None:
    """
    当日のシグナル数・上昇/下落上位銘柄を daily_summary に集計・保存する。
    """
    signal_count = conn.execute(
        "SELECT COUNT(*) FROM signals WHERE date = ?", (target_date,)
    ).fetchone()[0]

    top_gainers = conn.execute(
        """
        SELECT dp.code, s.name, dp.return_rate
        FROM daily_prices dp JOIN stocks s ON dp.code = s.code
        WHERE dp.date = ? AND dp.return_rate IS NOT NULL
        ORDER BY dp.return_rate DESC LIMIT 5
        """,
        (target_date,),
    ).fetchall()

    top_losers = conn.execute(
        """
        SELECT dp.code, s.name, dp.return_rate
        FROM daily_prices dp JOIN stocks s ON dp.code = s.code
        WHERE dp.date = ? AND dp.return_rate IS NOT NULL
        ORDER BY dp.return_rate ASC LIMIT 5
        """,
        (target_date,),
    ).fetchall()

    conn.execute(
        """
        INSERT INTO daily_summary (date, active_signals, top_gainers, top_losers)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(date) DO UPDATE SET
            active_signals = excluded.active_signals,
            top_gainers    = excluded.top_gainers,
            top_losers     = excluded.top_losers
        """,
        (
            target_date,
            signal_count,
            json.dumps(
                [{"code": r[0], "name": r[1], "return_rate": r[2]} for r in top_gainers],
                ensure_ascii=False,
            ),
            json.dumps(
                [{"code": r[0], "name": r[1], "return_rate": r[2]} for r in top_losers],
                ensure_ascii=False,
            ),
        ),
    )
    conn.commit()
    logger.info(f"daily_summary 更新: {target_date}, active_signals={signal_count}")


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

def generate(
    db_path: str,
    target_date: Optional[str] = None,
    graph_results: Optional[dict[str, Any]] = None,
) -> int:
    """
    全シグナルを生成して SQLite signals テーブルに保存し、
    daily_summary を更新する。

    Args:
        db_path: SQLite ファイルパス
        target_date: 'YYYY-MM-DD'。省略時は今日
        graph_results: graph.update_and_query() の戻り値。
                       None の場合は chains/regime_perf を要するシグナルをスキップ
    Returns:
        生成したシグナル総数
    """
    if target_date is None:
        target_date = date.today().isoformat()

    if graph_results is None:
        graph_results = {}

    chains = graph_results.get("chains", [])
    regime_perf = graph_results.get("regime_perf", {})

    logger.info(f"=== generate 開始: {target_date} ===")

    conn = sqlite3.connect(db_path)
    total = 0
    try:
        total += generate_causality_chain_signals(conn, target_date, chains)
        total += generate_fund_flow_signals(conn, target_date)
        total += generate_regime_shift_signals(conn, target_date, regime_perf)
        total += generate_cluster_breakout_signals(conn, target_date)
        total += generate_margin_squeeze_signals(conn, target_date)      # Phase 13
        total += generate_yen_sensitivity_signals(conn, target_date)   # Phase 13
        total += generate_credit_overheating_signal(conn, target_date) # Phase 16
        update_daily_summary(conn, target_date)
    finally:
        conn.close()

    logger.info(f"=== generate 完了: {total} シグナル ===")
    return total
