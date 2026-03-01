"""FastAPI アプリ定義"""
import logging
import os

import boto3
from fastapi import FastAPI, Response

from src.api.routers import backtest, network, prices, signals, stock, summary

logger = logging.getLogger(__name__)

app = FastAPI(title="nkflow API", version="0.1.0")

# CORS は Lambda Function URL 側で allowedOrigins=['*'] として設定済み

app.include_router(summary.router, prefix="/api")
app.include_router(prices.router, prefix="/api")
app.include_router(signals.router, prefix="/api")
app.include_router(network.router, prefix="/api")
app.include_router(stock.router, prefix="/api")
app.include_router(backtest.router, prefix="/api")  # Phase 14


@app.on_event("startup")
async def startup_event():
    """Lambda コールドスタート時に S3 から SQLite をダウンロードする。"""
    from src.api.storage import ensure_db
    try:
        ensure_db()
        logger.info("起動時 SQLite ロード完了")
    except Exception as e:
        logger.warning(f"起動時 SQLite ロード失敗 (リクエスト時にリトライ): {e}")


_EXT_CONTENT_TYPE = {
    ".html": "text/html; charset=utf-8",
    ".js":   "application/javascript",
    ".css":  "text/css",
    ".json": "application/json",
    ".png":  "image/png",
    ".svg":  "image/svg+xml",
    ".ico":  "image/x-icon",
    ".woff2": "font/woff2",
}


@app.get("/{path:path}")
async def serve_frontend(path: str) -> Response:
    """S3 からフロントエンドの静的ファイルを配信する。
    ファイルが存在しない場合は SPA ルーティング用に index.html を返す。
    """
    bucket = os.environ.get("S3_BUCKET", "")
    if not bucket:
        return Response(content="S3_BUCKET not configured", status_code=500)

    s3 = boto3.client("s3")
    key = f"frontend/{path}" if path else "frontend/index.html"

    suffix = "." + key.rsplit(".", 1)[-1] if "." in key.split("/")[-1] else ""
    content_type = _EXT_CONTENT_TYPE.get(suffix, "application/octet-stream")

    try:
        obj = s3.get_object(Bucket=bucket, Key=key)
        return Response(content=obj["Body"].read(), media_type=content_type)
    except Exception:
        # SPA フォールバック: Vue Router のクライアントサイドルーティング用
        try:
            obj = s3.get_object(Bucket=bucket, Key="frontend/index.html")
            return Response(content=obj["Body"].read(),
                            media_type="text/html; charset=utf-8")
        except Exception:
            return Response(content="Not Found", status_code=404)
