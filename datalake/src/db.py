"""バッチ処理用 DB ユーティリティ。"""
from contextlib import contextmanager

import duckdb


@contextmanager
def duckdb_sqlite(db_path: str, alias: str = "sq"):
    """DuckDB に SQLite ファイルをアタッチして接続を返す context manager。

    使い方::

        with duckdb_sqlite("/tmp/stocks.db") as duck:
            df = duck.execute("SELECT * FROM sq.daily_prices LIMIT 10").df()
    """
    duck = duckdb.connect()
    duck.execute("SET home_directory='/tmp'")
    duck.execute(f"ATTACH '{db_path}' AS {alias} (TYPE SQLITE)")
    try:
        yield duck
    finally:
        duck.close()
