"""
pytest 設定: テスト実行前にダミー環境変数をセットする。
src/config.py の os.environ["S3_BUCKET"] などが KeyError を起こさないようにする。
"""
import os

os.environ.setdefault("S3_BUCKET", "test-nkflow-bucket")
os.environ.setdefault("JQUANTS_API_KEY", "test-api-key")
