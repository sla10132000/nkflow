"""
Phase 14: バックテスト CLI スクリプト

ローカルの stocks.db に対してバックテストを実行する。
Lambda 外から直接実行する用途。

使用例:
    # 全シグナルタイプ・5日保有・直近6ヶ月
    python scripts/run_backtest.py \\
        --db /tmp/stocks.db \\
        --from 2024-06-01 --to 2024-12-31

    # causality_chain のみ・bullish・10日保有
    python scripts/run_backtest.py \\
        --db /tmp/stocks.db \\
        --from 2024-01-01 --to 2024-12-31 \\
        --signal-type causality_chain \\
        --direction bullish \\
        --holding 10 \\
        --min-confidence 0.6

    # 全シグナルタイプを順に比較
    python scripts/run_backtest.py \\
        --db /tmp/stocks.db \\
        --from 2024-01-01 --to 2024-12-31 \\
        --all-types
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.migrate_phase14 import migrate
from src.batch.backtest import run_backtest

SIGNAL_TYPES = [
    "causality_chain",
    "fund_flow",
    "regime_shift",
    "lead_lag",
    "cluster_breakout",
]


def _print_result(name: str, result: dict) -> None:
    m = result["metrics"]
    print(f"\n{'─' * 56}")
    print(f"  {name}  (run_id={result['run_id']})")
    print(f"{'─' * 56}")
    print(f"  対象トレード数:    {m['total_trades']}")
    print(f"  勝ち数:           {m['winning_trades']}")
    print(f"  勝率:             {m['win_rate']:.1%}")
    print(f"  平均リターン:     {m['avg_return']:.4%}")
    print(f"  累計リターン:     {m['total_return']:.4%}")
    print(f"  最大ドローダウン: {m['max_drawdown']:.4%}")
    sharpe = m["sharpe_ratio"]
    print(f"  シャープレシオ:   {sharpe:.4f}" if sharpe is not None else "  シャープレシオ:   N/A")


def main() -> None:
    parser = argparse.ArgumentParser(description="nkflow バックテスト CLI")
    parser.add_argument("--db", default="/tmp/stocks.db", help="SQLite ファイルパス")
    parser.add_argument("--from", dest="from_date", required=True, help="開始日 YYYY-MM-DD")
    parser.add_argument("--to", dest="to_date", required=True, help="終了日 YYYY-MM-DD")
    parser.add_argument("--holding", type=int, default=5, help="保有営業日数 (デフォルト: 5)")
    parser.add_argument("--signal-type", default=None, help="シグナルタイプ (省略=全種)")
    parser.add_argument("--direction", choices=["bullish", "bearish"], default=None)
    parser.add_argument("--min-confidence", type=float, default=0.0, help="最低 confidence (0.0〜1.0)")
    parser.add_argument("--all-types", action="store_true", help="全シグナルタイプを個別に比較")
    parser.add_argument("--name", default=None, help="バックテスト名 (省略時は自動生成)")
    parser.add_argument("--json", action="store_true", help="結果を JSON で出力")
    args = parser.parse_args()

    # マイグレーション (べき等)
    migrate(args.db)

    results = []

    if args.all_types:
        for stype in SIGNAL_TYPES:
            run_name = args.name or f"{stype} {args.from_date}〜{args.to_date} {args.holding}d"
            result = run_backtest(
                db_path=args.db,
                name=run_name,
                from_date=args.from_date,
                to_date=args.to_date,
                holding_days=args.holding,
                signal_type=stype,
                direction_filter=args.direction,
                min_confidence=args.min_confidence,
            )
            results.append((run_name, result))
    else:
        run_name = (
            args.name
            or f"{args.signal_type or 'all'} {args.from_date}〜{args.to_date} {args.holding}d"
        )
        result = run_backtest(
            db_path=args.db,
            name=run_name,
            from_date=args.from_date,
            to_date=args.to_date,
            holding_days=args.holding,
            signal_type=args.signal_type,
            direction_filter=args.direction,
            min_confidence=args.min_confidence,
        )
        results.append((run_name, result))

    if args.json:
        print(json.dumps([{"name": n, **r} for n, r in results], ensure_ascii=False, indent=2))
    else:
        for name, result in results:
            _print_result(name, result)
        print()


if __name__ == "__main__":
    main()
