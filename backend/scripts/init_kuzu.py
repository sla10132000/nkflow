"""KùzuDBスキーマ作成"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def init_kuzu(db_path: str = "/tmp/kuzu_db"):
    import kuzu

    parent = os.path.dirname(os.path.abspath(db_path))
    os.makedirs(parent, exist_ok=True)
    db = kuzu.Database(db_path)
    conn = kuzu.Connection(db)

    # ==================== ノード ====================
    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS Stock(
            code STRING,
            name STRING,
            sector STRING,
            market_cap_tier STRING,
            community_id INT64,
            PRIMARY KEY(code)
        )
    """)

    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS Sector(
            name STRING,
            PRIMARY KEY(name)
        )
    """)

    conn.execute("""
        CREATE NODE TABLE IF NOT EXISTS TradingDay(
            date DATE,
            nikkei_close DOUBLE,
            nikkei_return DOUBLE,
            regime STRING,
            PRIMARY KEY(date)
        )
    """)

    # ==================== エッジ ====================

    # 銘柄 → セクター
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS BELONGS_TO(
            FROM Stock TO Sector
        )
    """)

    # 相関 (stock_a < stock_b で正規化)
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS CORRELATED(
            FROM Stock TO Stock,
            coefficient DOUBLE,
            period STRING,
            calc_date DATE
        )
    """)

    # グレンジャー因果 (方向あり)
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS GRANGER_CAUSES(
            FROM Stock TO Stock,
            lag_days INT64,
            p_value DOUBLE,
            f_stat DOUBLE,
            period STRING,
            calc_date DATE
        )
    """)

    # リードラグ (先行・遅行関係)
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS LEADS(
            FROM Stock TO Stock,
            lag_days INT64,
            cross_corr DOUBLE,
            period STRING,
            calc_date DATE
        )
    """)

    # セクター間資金フロー
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS FUND_FLOW(
            FROM Sector TO Sector,
            direction STRING,
            volume_delta DOUBLE,
            return_spread DOUBLE,
            date DATE
        )
    """)

    # 日次取引記録
    conn.execute("""
        CREATE REL TABLE IF NOT EXISTS TRADED_ON(
            FROM Stock TO TradingDay,
            return_rate DOUBLE,
            price_range DOUBLE,
            volume INT64,
            relative_strength DOUBLE
        )
    """)

    conn.close()
    print(f"KùzuDBスキーマを初期化しました: {db_path}")
    return db


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/kuzu_db"
    init_kuzu(db_path)
