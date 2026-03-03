"""GET /api/news, GET /api/news/summary — Phase 18"""
from sqlite3 import Connection
from typing import Optional

from fastapi import APIRouter, Depends

from src.api.storage import get_connection

router = APIRouter()


@router.get("/news")
def get_news(
    date: Optional[str] = None,
    ticker: Optional[str] = None,
    limit: int = 50,
    conn: Connection = Depends(get_connection),
):
    """ニュース記事一覧を返す。

    Args:
        date: 絞り込み対象日 (YYYY-MM-DD)。省略時は全期間。
        ticker: 銘柄コードで絞り込み (news_ticker_map 経由)。
        limit: 最大返却件数 (デフォルト 50)。
    """
    if ticker:
        rows = conn.execute(
            """
            SELECT a.id, a.published_at, a.source, a.source_name,
                   a.title, a.url, a.language, a.image_url, a.sentiment
            FROM news_articles a
            JOIN news_ticker_map m ON a.id = m.article_id
            WHERE m.ticker = ?
              AND (? IS NULL OR date(a.published_at) = ?)
            ORDER BY a.published_at DESC
            LIMIT ?
            """,
            (ticker, date, date, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            """
            SELECT id, published_at, source, source_name,
                   title, url, language, image_url, sentiment
            FROM news_articles
            WHERE (? IS NULL OR date(published_at) = ?)
            ORDER BY published_at DESC
            LIMIT ?
            """,
            (date, date, limit),
        ).fetchall()

    return [dict(row) for row in rows]


@router.get("/news/summary")
def get_news_summary(
    date: Optional[str] = None,
    conn: Connection = Depends(get_connection),
):
    """日次ニュースまとめ (件数・ソース分布) を返す。

    Args:
        date: 集計対象日 (YYYY-MM-DD)。省略時は全期間。
    """
    total = conn.execute(
        """
        SELECT COUNT(*) FROM news_articles
        WHERE (? IS NULL OR date(published_at) = ?)
        """,
        (date, date),
    ).fetchone()[0]

    sources = conn.execute(
        """
        SELECT source, COUNT(*) AS count
        FROM news_articles
        WHERE (? IS NULL OR date(published_at) = ?)
        GROUP BY source
        ORDER BY count DESC
        LIMIT 10
        """,
        (date, date),
    ).fetchall()

    return {
        "date": date,
        "total": total,
        "sources": [dict(r) for r in sources],
    }
