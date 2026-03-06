"""Raw data layer: API レスポンスを S3 に不変ファイルとして保存する"""
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

import boto3
from botocore.exceptions import ClientError

from src.config import S3_BUCKET, S3_RAW_PREFIX

logger = logging.getLogger(__name__)


def save_raw(
    source: str,
    data_type: str,
    date_str: str,
    payload: Any,
    *,
    overwrite: bool = False,
) -> Optional[str]:
    """API レスポンスを S3 に JSON として保存する。

    Args:
        source: データソース名 (例: "jquants", "yahoo_finance")
        data_type: データ種別 (例: "daily_prices", "exchange_rates")
        date_str: 対象日 (YYYY-MM-DD)
        payload: 保存するデータ (JSON シリアライズ可能な任意オブジェクト)
        overwrite: True の場合、既存ファイルを上書き (デフォルト: False)

    Returns:
        保存した S3 キー。失敗時は None。
    """
    s3_key = f"{S3_RAW_PREFIX}/{source}/{data_type}/{date_str}.json"

    try:
        import pandas as pd

        if isinstance(payload, pd.DataFrame):
            payload = payload.to_dict(orient="records")
    except ImportError:
        pass

    try:
        s3 = boto3.client("s3")

        if not overwrite:
            try:
                s3.head_object(Bucket=S3_BUCKET, Key=s3_key)
                logger.info(f"raw データ既存のためスキップ: s3://{S3_BUCKET}/{s3_key}")
                return s3_key
            except ClientError as e:
                if e.response["Error"]["Code"] != "404":
                    raise

        body = json.dumps(
            {
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "source": source,
                "data_type": data_type,
                "date": date_str,
                "data": payload,
            },
            ensure_ascii=False,
            default=str,
        )

        s3.put_object(
            Bucket=S3_BUCKET,
            Key=s3_key,
            Body=body.encode("utf-8"),
            ContentType="application/json; charset=utf-8",
        )
        logger.info(f"raw データ保存: s3://{S3_BUCKET}/{s3_key}")
        return s3_key
    except Exception as e:
        logger.warning(f"raw データ保存失敗 ({s3_key}): {e}")
        return None
