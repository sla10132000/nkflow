"""Phase 27: コモディティ・スーパーサイクル分析 — config 駆動のフェーズ定義

スーパーサイクルは数十年単位の構造的判断であり、短期指標による自動検出は不適切。
フェーズ位置は四半期ごとに人手でレビュー・更新する。

フェーズモデル (4-phase):
  Phase 1: 回復    — 投資不足が顕在化、価格底打ち
  Phase 2: 加速    — 需要>供給が定着、価格上昇加速
  Phase 3: 成熟    — 供給が追いつく、価格ピーク→下落
  Phase 4: 底形成  — 過剰供給の調整、投資凍結
"""

# フェーズ定義
PHASES: dict[int, dict] = {
    1: {"name": "回復",   "name_en": "Recovery",     "color": "#3b82f6", "description": "投資不足が顕在化、価格底打ち"},
    2: {"name": "加速",   "name_en": "Acceleration", "color": "#10b981", "description": "需要>供給が定着、価格上昇加速"},
    3: {"name": "成熟",   "name_en": "Maturity",     "color": "#f59e0b", "description": "供給が追いつく、価格ピーク→下落"},
    4: {"name": "底形成", "name_en": "Bottom",       "color": "#ef4444", "description": "過剰供給の調整、投資凍結"},
}

# コモディティ表示ラベル (ticker → 日本語ラベル)
COMMODITY_LABELS: dict[str, str] = {
    "GC=F":  "金",
    "CL=F":  "原油 (WTI)",
    "SI=F":  "銀",
    "HG=F":  "銅",
    "NG=F":  "天然ガス",
    "ZW=F":  "小麦",
    "ZC=F":  "コーン",
    "URA":   "ウラン (ETF)",
    "ALI=F": "アルミ",
    "LIT":   "リチウム (ETF)",
}

# セクター別フェーズ (position: 1.0〜4.99 の連続値)
# 例: 2.3 = Phase 2 前半〜中盤、2.7 = Phase 2 後半
# 最終更新: 2026-03-07
SECTOR_PHASES: dict[str, dict] = {
    "energy":          {"phase": 2, "position": 2.3, "updated": "2026-03-07"},
    "base_metals":     {"phase": 2, "position": 2.4, "updated": "2026-03-07"},
    "precious_metals": {"phase": 3, "position": 3.2, "updated": "2026-03-07"},
    "battery_metals":  {"phase": 1, "position": 1.3, "updated": "2026-03-07"},
    "agriculture":     {"phase": 2, "position": 2.1, "updated": "2026-03-07"},
}

# コモディティ個別フェーズオーバーライド (セクター平均と異なる場合のみ定義)
COMMODITY_PHASES: dict[str, dict] = {
    "GC=F": {"phase": 3, "position": 3.5},  # 金は貴金属平均より進んでいる
    "URA":  {"phase": 2, "position": 2.7},  # ウランはエネルギー平均より加速
    "LIT":  {"phase": 1, "position": 1.2},  # リチウムは2023年の暴落から回復中
}

# シナリオ分析
SCENARIOS: list[dict] = [
    {
        "id": "main",
        "name": "段階的上昇",
        "probability": 50,
        "peak": "2030-2033",
        "description": "銅・ウランが需給逼迫でリード。エネルギー転換投資が本格化し、2030年代前半にピーク。その後新規鉱山・インフラ稼働で供給が追いつく。",
        "key_drivers": ["銅・ウランの需給逼迫", "エネルギー転換投資加速", "インフレ継続"],
    },
    {
        "id": "early_peak",
        "name": "早期ピーク",
        "probability": 25,
        "peak": "2027-2028",
        "description": "世界的景気後退でコモディティ需要が急減。AI による省エネ・効率化が想定以上に進展し、2027〜2028年に早期ピークを迎える。",
        "key_drivers": ["世界景気後退", "AI省エネ効果", "需要急減"],
    },
    {
        "id": "extended",
        "name": "延長・過熱",
        "probability": 25,
        "peak": "2035年以降",
        "description": "地政学リスクの激化・資源ナショナリズムの加速により供給が制約。中央銀行の利下げで投機資金が流入し、バブル的様相を呈する。",
        "key_drivers": ["地政学リスク激化", "資源ナショナリズム", "利下げによる投機流入"],
    },
]

# セクター間相関 (投資示唆)
CORRELATIONS: list[dict] = [
    {
        "from_sector": "energy",
        "to_sector": "battery_metals",
        "type": "positive_lag",
        "description": "原油高 → EV加速 → 銅・リチウム需要増（遅延相関）",
    },
    {
        "from_sector": "energy",
        "to_sector": "base_metals",
        "type": "negative",
        "description": "ウラン高 → 原発再稼働 → 天然ガス需要減（代替相関）",
    },
    {
        "from_sector": "precious_metals",
        "to_sector": "precious_metals",
        "type": "lag",
        "description": "金高 → 銀が遅れて追随（貴金属内の位相差）",
    },
]

# 設定の最終更新日
CONFIG_UPDATED = "2026-03-07"
