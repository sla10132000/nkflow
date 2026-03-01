"""環境変数と定数"""
import os

# AWS
S3_BUCKET = os.environ["S3_BUCKET"]
S3_SQLITE_KEY = "data/stocks.db"
S3_KUZU_KEY = "data/kuzu_db.tar.gz"

# J-Quants (SSM Parameter Store から取得)
# Lambda 起動時に storage.get_api_key() で SSM から読み込む
JQUANTS_API_KEY = os.environ.get("JQUANTS_API_KEY", "")
# J-Quants プラン: free / light / standard / premium
# free: 過去2年・直近12週除外・5 req/min
JQUANTS_PLAN = os.environ.get("JQUANTS_PLAN", "free")
# API レート制限 (秒/リクエスト): free=12秒 (5req/min), それ以外=0
JQUANTS_RATE_LIMIT_SEC: float = 25.0 if JQUANTS_PLAN == "free" else 0.0

# ローカルパス (Lambda の /tmp)
SQLITE_PATH = os.environ.get("SQLITE_PATH", "/tmp/stocks.db")
KUZU_PATH = os.environ.get("KUZU_PATH", "/tmp/kuzu_db")

# 分析パラメータ
CORRELATION_PERIODS = [20, 60, 120]
GRANGER_MAX_LAG = 5
GRANGER_P_THRESHOLD = 0.05
CORRELATION_THRESHOLD = 0.5
COMMUNITY_RESOLUTION = 1.0
