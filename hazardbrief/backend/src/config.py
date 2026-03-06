"""HazardBrief API — 環境変数・定数"""
import os

# AWS
S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_SQLITE_KEY = "data/hazardbrief.db"

# Auth0
AUTH0_DOMAIN = os.environ.get("AUTH0_DOMAIN", "")
AUTH0_AUDIENCE = os.environ.get("AUTH0_AUDIENCE", "")

# 外部 API
GSI_GEOCODER_URL = "https://msearch.gsi.go.jp/address-search/AddressSearch"
REINFOLIB_BASE_URL = "https://www.reinfolib.mlit.go.jp/ex-api/external"
REINFOLIB_API_KEY = os.environ.get("REINFOLIB_API_KEY", "")
GSI_ELEVATION_URL = "https://cyberjapandata2.gsi.go.jp/general/dem/scripts/getelevation.php"

# ハザードレポートキャッシュ有効期間 (秒): 90日
HAZARD_CACHE_TTL_SECONDS = 90 * 24 * 60 * 60


def _resolve_local_path(env_key: str, default_path: str) -> str:
    """Worktree 内で実行されている場合、/tmp/hazardbrief-<name>/ 配下にパスを分離する。"""
    if explicit := os.environ.get(env_key):
        return explicit
    cwd = os.getcwd()
    marker = "/.claude/worktrees/"
    if marker in cwd:
        wt_name = cwd.split(marker)[1].split("/")[0]
        base_dir = f"/tmp/hazardbrief-{wt_name}"
        os.makedirs(base_dir, exist_ok=True)
        return os.path.join(base_dir, os.path.basename(default_path))
    return default_path


# ローカルパス
DB_PATH = _resolve_local_path("SQLITE_PATH", "/tmp/hazardbrief.db")
