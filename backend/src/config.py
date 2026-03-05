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
JQUANTS_PLAN = os.environ.get("JQUANTS_PLAN", "standard")
# API レート制限 (秒/リクエスト): free=25秒 (5req/min), それ以外=0
JQUANTS_RATE_LIMIT_SEC: float = 25.0 if JQUANTS_PLAN == "free" else 0.0


def _resolve_local_path(env_key: str, default_path: str) -> str:
    """Worktree 内で実行されている場合、/tmp/nkflow-<name>/ 配下にパスを分離する。

    環境変数が明示的に設定されていればそちらを優先する。
    Lambda 環境では worktree マーカーが存在しないため /tmp/ 直下のまま。
    """
    if explicit := os.environ.get(env_key):
        return explicit
    cwd = os.getcwd()
    marker = "/.claude/worktrees/"
    if marker in cwd:
        wt_name = cwd.split(marker)[1].split("/")[0]
        base_dir = f"/tmp/nkflow-{wt_name}"
        os.makedirs(base_dir, exist_ok=True)
        return os.path.join(base_dir, os.path.basename(default_path))
    return default_path


# ローカルパス (Lambda の /tmp)
# Worktree 内ではセッションごとに分離される
SQLITE_PATH = _resolve_local_path("SQLITE_PATH", "/tmp/stocks.db")
KUZU_PATH = _resolve_local_path("KUZU_PATH", "/tmp/kuzu_db")

# SNS (Phase 12)
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")

# 米国株価指数 (Phase 20)
US_INDEX_TICKERS: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ Composite",
}
US_INDEX_INITIAL_PERIOD = "10y"

# 米国セクター ETF (Phase 23b): Select Sector SPDR ETFs
US_SECTOR_ETF_TICKERS: dict[str, dict[str, str]] = {
    "XLK":  {"name": "Technology Select Sector SPDR",              "sector": "テクノロジー"},
    "XLF":  {"name": "Financial Select Sector SPDR",               "sector": "金融"},
    "XLV":  {"name": "Health Care Select Sector SPDR",             "sector": "ヘルスケア"},
    "XLE":  {"name": "Energy Select Sector SPDR",                  "sector": "エネルギー"},
    "XLI":  {"name": "Industrial Select Sector SPDR",              "sector": "資本財"},
    "XLY":  {"name": "Consumer Discretionary Select Sector SPDR",  "sector": "一般消費財"},
    "XLP":  {"name": "Consumer Staples Select Sector SPDR",        "sector": "生活必需品"},
    "XLU":  {"name": "Utilities Select Sector SPDR",               "sector": "公益"},
    "XLB":  {"name": "Materials Select Sector SPDR",               "sector": "素材"},
    "XLRE": {"name": "Real Estate Select Sector SPDR",             "sector": "不動産"},
    "XLC":  {"name": "Communication Services Select Sector SPDR",  "sector": "通信"},
}

# 恐怖指数 (Phase 21): VIX は us_indices テーブルに保存
FEAR_INDEX_TICKERS: dict[str, str] = {
    "^VIX": "VIX",
}
# BTC Fear & Greed Index
ALTERNATIVE_ME_FNG_URL = "https://api.alternative.me/fng/"

# 分析パラメータ — 相関・因果
CORRELATION_PERIODS = [20, 60, 120]
GRANGER_MAX_LAG = 5
GRANGER_P_THRESHOLD = 0.05
CORRELATION_THRESHOLD = 0.5
COMMUNITY_RESOLUTION = 1.0

# 分析パラメータ — 統計分析ウィンドウ (batch/statistics.py で使用)
GRANGER_WINDOW = 60          # グレンジャー検定に使う直近営業日数
LEAD_LAG_MAX = 5             # クロス相関の最大ラグ数
LEAD_LAG_THRESHOLD = 0.3     # クロス相関の最低閾値
FUND_FLOW_WINDOW = 20        # 資金フローの比較ベースライン日数
REGIME_SHORT_WINDOW = 5      # レジーム判定: 直近ボラ
REGIME_LONG_WINDOW = 20      # レジーム判定: 比較ベースボラ
MAX_GRANGER_STOCKS = 100     # 直近出来高上位 N 銘柄に限定
