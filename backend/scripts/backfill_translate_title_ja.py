"""既存の news_articles で title_ja が未設定の記事を AWS Translate で翻訳するバックフィル。

使い方:
    python backend/scripts/backfill_translate_title_ja.py [db_path]

デフォルトの db_path は /tmp/stocks.db。
実行後は make push-db で S3 に反映すること。
"""
import logging
import sqlite3
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

import boto3

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

BATCH_SIZE = 50
MAX_WORKERS = 8


def _translate_batch(titles: list[str]) -> list[Optional[str]]:
    translate = boto3.client("translate", region_name="ap-northeast-1")
    results: list[Optional[str]] = [None] * len(titles)

    def _one(idx: int, text: str) -> tuple[int, Optional[str]]:
        try:
            resp = translate.translate_text(
                Text=text,
                SourceLanguageCode="en",
                TargetLanguageCode="ja",
            )
            return idx, resp["TranslatedText"]
        except Exception as e:
            logger.warning(f"翻訳失敗 (idx={idx}): {e}")
            return idx, None

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(_one, i, t): i for i, t in enumerate(titles)}
        for future in as_completed(futures):
            idx, translated = future.result()
            results[idx] = translated

    return results


def backfill(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    try:
        # title_ja が未設定の英語記事を取得
        rows = conn.execute(
            """
            SELECT id, title, language FROM news_articles
            WHERE (title_ja IS NULL OR title_ja = '')
            ORDER BY published_at DESC
            """
        ).fetchall()

        logger.info(f"翻訳対象: {len(rows)} 件")
        if not rows:
            logger.info("翻訳対象なし。終了。")
            return

        updated = 0
        for start in range(0, len(rows), BATCH_SIZE):
            batch = rows[start : start + BATCH_SIZE]

            english = [(i, r[0], r[1]) for i, r in enumerate(batch) if r[2] != "Japanese"]
            japanese = [(i, r[0]) for i, r in enumerate(batch) if r[2] == "Japanese"]

            translated: dict[int, Optional[str]] = {}

            # 日本語記事はそのまま
            for i, title in japanese:
                translated[i] = title

            # 英語記事は翻訳
            if english:
                indices = [e[0] for e in english]
                titles = [e[1] for e in english]
                results = _translate_batch(titles)
                for j, result in enumerate(results):
                    translated[indices[j]] = result

            # DB 更新
            for i, row in enumerate(batch):
                article_id = row[0]
                title_ja = translated.get(i)
                if title_ja:
                    conn.execute(
                        "UPDATE news_articles SET title_ja = ? WHERE id = ?",
                        (title_ja, article_id),
                    )
                    updated += 1

            conn.commit()
            done = min(start + BATCH_SIZE, len(rows))
            logger.info(f"進捗: {done}/{len(rows)} 件処理済み")

        logger.info(f"完了: {updated} 件更新しました")
    finally:
        conn.close()


if __name__ == "__main__":
    db_path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/stocks.db"
    backfill(db_path)
