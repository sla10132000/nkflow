"""API 用 環境変数と定数"""
import os


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
