"""API + バッチ共通 環境変数と定数"""
import os

# AWS
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_SQLITE_KEY = "data/stocks.db"
S3_KUZU_KEY = "data/kuzu_db.tar.gz"

# J-Quants (SSM Parameter Store から取得)
JQUANTS_API_KEY = os.environ.get("JQUANTS_API_KEY", "")
JQUANTS_PLAN = os.environ.get("JQUANTS_PLAN", "standard")

# SNS (Phase 12)
SNS_TOPIC_ARN = os.environ.get("SNS_TOPIC_ARN", "")


def _resolve_local_path(env_key: str, default_path: str) -> str:
    """Worktree 内で実行されている場合、/tmp/nkflow-<name>/ 配下にパスを分離する。"""
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


# ローカルパス
SQLITE_PATH = _resolve_local_path("SQLITE_PATH", "/tmp/stocks.db")
KUZU_PATH = _resolve_local_path("KUZU_PATH", "/tmp/kuzu_db")

# 米国株価指数 (Phase 20)
US_INDEX_TICKERS: dict[str, str] = {
    "^GSPC": "S&P 500",
    "^DJI": "Dow Jones",
    "^IXIC": "NASDAQ Composite",
}
US_INDEX_INITIAL_PERIOD = "10y"

# 恐怖指数 (Phase 21)
FEAR_INDEX_TICKERS: dict[str, str] = {
    "^VIX": "VIX",
}
ALTERNATIVE_ME_FNG_URL = "https://api.alternative.me/fng/"

# 分析パラメータ — 相関・因果
CORRELATION_PERIODS = [20, 60, 120]
GRANGER_MAX_LAG = 5
GRANGER_P_THRESHOLD = 0.05
CORRELATION_THRESHOLD = 0.5
COMMUNITY_RESOLUTION = 1.0

# 分析パラメータ — 統計分析ウィンドウ
GRANGER_WINDOW = 60
LEAD_LAG_MAX = 5
LEAD_LAG_THRESHOLD = 0.3
FUND_FLOW_WINDOW = 20
REGIME_SHORT_WINDOW = 5
REGIME_LONG_WINDOW = 20
MAX_GRANGER_STOCKS = 100

# スーパーサイクル セクター定義 (Phase 27)
SUPERCYCLE_SECTORS: dict[str, dict] = {
    "energy":          {"label": "エネルギー",     "tickers": ["CL=F", "NG=F", "URA"]},
    "base_metals":     {"label": "ベースメタル",    "tickers": ["HG=F", "ALI=F"]},
    "precious_metals": {"label": "貴金属",         "tickers": ["GC=F", "SI=F"]},
    "battery_metals":  {"label": "バッテリー金属",  "tickers": ["LIT"]},
    "agriculture":     {"label": "農産物",         "tickers": ["ZW=F", "ZC=F"]},
}

# 米国セクター ETF (Phase 23b): API ルーターで参照
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
