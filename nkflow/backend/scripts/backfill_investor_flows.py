"""
投資主体別フロー バックフィルスクリプト

J-Quants API から過去52週分の投資主体別売買動向を取得し、
指標計算・シグナル生成まで実行する。

実行方法:
    cd /Volumes/Data/work/prj/code/nkflow
    SQLITE_PATH=/tmp/stocks.db .venv/bin/python \
        nkflow/backend/scripts/backfill_investor_flows.py
"""
import os
import sqlite3
import sys
from datetime import date, timedelta

# datalake モジュールへのパスを追加
# worktree 構造: <worktree_root>/nkflow/backend/scripts/
#                <worktree_root>/datalake/
_script_dir = os.path.dirname(os.path.abspath(__file__))
WORKTREE_ROOT = os.path.abspath(os.path.join(_script_dir, "../../../"))
sys.path.insert(0, os.path.join(WORKTREE_ROOT, "nkflow/backend"))
sys.path.insert(0, os.path.join(WORKTREE_ROOT, "datalake"))  # datalake を先頭に (src パッケージが優先)

# datalake/src/config.py が要求する最低限の環境変数をインポート前に設定
os.environ.setdefault("S3_BUCKET", "nkflow-data-placeholder")
os.environ.setdefault("KUZU_PATH", "/tmp/kuzu_db")
os.environ.setdefault("JQUANTS_API_KEY", "")

from src.ingestion import jquants as jquants_mod
from src.transform import statistics as stats_mod
from src.signals import generator as sig_mod

DB_PATH = os.environ.get("SQLITE_PATH", "/tmp/stocks.db")

# 52週前 (約1年分)
today = date.today()
from_date = (today - timedelta(weeks=52)).strftime("%Y-%m-%d")
to_date = today.strftime("%Y-%m-%d")

print(f"DB: {DB_PATH}")
print(f"取得期間: {from_date} ~ {to_date}")

conn = sqlite3.connect(DB_PATH)
conn.row_factory = sqlite3.Row

try:
    # Step 1: データ取得
    print("\n[Step 1] 投資主体別売買動向を取得中...")
    rows = jquants_mod.fetch_investor_flows(conn, from_date, to_date)
    print(f"  → {rows} 件保存")

    conn.close()

    # Step 2: 指標計算 (db_path, target_date シグネチャ)
    print("\n[Step 2] 指標を計算中...")
    indicators = stats_mod.compute_investor_flow_indicators(DB_PATH, to_date)
    print(f"  → {indicators} 件保存")

    # Step 3: シグナル生成 (db_path, target_date シグネチャ)
    print("\n[Step 3] シグナルを生成中...")
    signals = sig_mod.generate_investor_flow_signals(DB_PATH, to_date)
    print(f"  → {signals} 件生成")

    # 確認
    conn2 = sqlite3.connect(DB_PATH)
    week_count = conn2.execute("SELECT COUNT(DISTINCT week_end) FROM investor_flow_weekly").fetchone()[0]
    ind_count = conn2.execute("SELECT COUNT(*) FROM investor_flow_indicators").fetchone()[0]
    latest = conn2.execute("SELECT week_end FROM investor_flow_indicators ORDER BY week_end DESC LIMIT 1").fetchone()
    conn2.close()
    print(f"\n=== 完了 ===")
    print(f"  週次フロー: {week_count} 週分")
    print(f"  指標:       {ind_count} 件")
    print(f"  最新週:     {latest[0] if latest else 'N/A'}")

except Exception:
    try:
        conn.close()
    except Exception:
        pass
    raise
