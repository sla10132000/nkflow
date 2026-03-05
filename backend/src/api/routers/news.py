"""GET /api/news, GET /api/news/summary, GET /api/news/themes — Phase 18/24"""
from sqlite3 import Connection
from typing import Optional

from fastapi import APIRouter, Depends

from src.api.storage import get_connection

router = APIRouter()

_DATE_FILTER = "(? IS NULL OR date(published_at, '+9 hours') = ?)"


@router.get("/news")
def get_news(
    date: Optional[str] = None,
    ticker: Optional[str] = None,
    category: Optional[str] = None,
    limit: int = 50,
    conn: Connection = Depends(get_connection),
):
    """ニュース記事一覧を返す。

    Args:
        date: 絞り込み対象日 (YYYY-MM-DD)。省略時は全期間。
        ticker: 銘柄コードで絞り込み (news_ticker_map 経由)。
        category: テーマで絞り込み。
        limit: 最大返却件数 (デフォルト 50)。
    """
    base_cols = """a.id, a.published_at, a.source, a.source_name,
                   a.title, a.title_ja, a.url, a.language,
                   a.image_url, a.sentiment, a.category"""

    if ticker:
        rows = conn.execute(
            f"""
            SELECT {base_cols},
                   GROUP_CONCAT(m2.ticker) AS tickers
            FROM news_articles a
            JOIN news_ticker_map m ON a.id = m.article_id
            LEFT JOIN news_ticker_map m2 ON a.id = m2.article_id
            WHERE m.ticker = ?
              AND {_DATE_FILTER}
              AND (? IS NULL OR a.category = ?)
            GROUP BY a.id
            ORDER BY a.published_at DESC
            LIMIT ?
            """,
            (ticker, date, date, category, category, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            f"""
            SELECT {base_cols},
                   (SELECT GROUP_CONCAT(m.ticker) FROM news_ticker_map m
                    WHERE m.article_id = a.id) AS tickers
            FROM news_articles a
            WHERE {_DATE_FILTER}
              AND (? IS NULL OR a.category = ?)
            ORDER BY a.published_at DESC
            LIMIT ?
            """,
            (date, date, category, category, limit),
        ).fetchall()

    return [dict(row) for row in rows]


@router.get("/news/summary")
def get_news_summary(
    date: Optional[str] = None,
    conn: Connection = Depends(get_connection),
):
    """日次ニュースまとめ (件数・ソース分布・センチメント・テーマ) を返す。"""
    total = conn.execute(
        f"SELECT COUNT(*) FROM news_articles WHERE {_DATE_FILTER}",
        (date, date),
    ).fetchone()[0]

    sources = conn.execute(
        f"""
        SELECT source_name AS source, COUNT(*) AS count
        FROM news_articles
        WHERE {_DATE_FILTER}
        GROUP BY source_name
        ORDER BY count DESC
        LIMIT 10
        """,
        (date, date),
    ).fetchall()

    # センチメント分布
    sentiment_dist = conn.execute(
        f"""
        SELECT
            SUM(CASE WHEN sentiment > 0.1 THEN 1 ELSE 0 END) AS positive,
            SUM(CASE WHEN sentiment < -0.1 THEN 1 ELSE 0 END) AS negative,
            SUM(CASE WHEN sentiment IS NULL OR (sentiment >= -0.1 AND sentiment <= 0.1) THEN 1 ELSE 0 END) AS neutral
        FROM news_articles
        WHERE {_DATE_FILTER}
        """,
        (date, date),
    ).fetchone()

    # テーマ別件数
    categories = conn.execute(
        f"""
        SELECT category, COUNT(*) AS count
        FROM news_articles
        WHERE {_DATE_FILTER} AND category IS NOT NULL
        GROUP BY category
        ORDER BY count DESC
        """,
        (date, date),
    ).fetchall()

    return {
        "date": date,
        "total": total,
        "sources": [dict(r) for r in sources],
        "sentiment_dist": dict(sentiment_dist) if sentiment_dist else {"positive": 0, "negative": 0, "neutral": 0},
        "categories": [dict(r) for r in categories],
    }
