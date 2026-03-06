"""Phase 24b/c/d: ニュース記事の後処理 — センチメント分析・ティッカー抽出・テーマ分類"""
import logging
import re
import sqlite3

logger = logging.getLogger(__name__)

# ── センチメント辞書 (Phase 24b) ────────────────────────────────────────

POSITIVE_JA = {
    "上昇", "好調", "増益", "増収", "最高益", "反発", "上方修正", "買い越し",
    "黒字", "急伸", "堅調", "回復", "改善", "高値", "過去最高", "増配",
    "急騰", "続伸", "成長", "拡大", "上振れ", "好決算", "増額",
}
NEGATIVE_JA = {
    "下落", "急落", "減益", "減収", "赤字", "下方修正", "売り越し", "暴落",
    "低迷", "悪化", "不振", "安値", "急減", "続落", "縮小", "減額",
    "下振れ", "損失", "破綻", "減配", "無配", "債務超過",
}
POSITIVE_EN = {
    "surge", "rally", "gain", "rise", "profit", "upgrade", "bullish",
    "growth", "beat", "outperform", "recovery", "record high", "boom",
}
NEGATIVE_EN = {
    "fall", "drop", "loss", "decline", "bearish", "downgrade", "crash",
    "slump", "miss", "underperform", "recession", "plunge", "tumble",
}


def analyze_sentiment(title_ja: str | None, title: str | None) -> float:
    """タイトルから辞書ベースのセンチメントスコアを算出する。

    Returns:
        -1.0 ~ +1.0 のスコア。ヒットなしは 0.0。
    """
    pos = 0
    neg = 0

    if title_ja:
        for w in POSITIVE_JA:
            if w in title_ja:
                pos += 1
        for w in NEGATIVE_JA:
            if w in title_ja:
                neg += 1

    if title:
        lower = title.lower()
        for w in POSITIVE_EN:
            if w in lower:
                pos += 1
        for w in NEGATIVE_EN:
            if w in lower:
                neg += 1

    total = pos + neg
    if total == 0:
        return 0.0
    return max(-1.0, min(1.0, (pos - neg) / total))


# ── テーマ辞書 (Phase 24d) ─────────────────────────────────────────────

THEMES: dict[str, set[str]] = {
    "決算": {"決算", "増益", "減益", "業績", "通期", "四半期", "上方修正", "下方修正",
             "最終利益", "営業利益", "経常", "配当", "earnings", "dividend"},
    "金融政策": {"日銀", "利上げ", "利下げ", "金融緩和", "金融引き締め", "マイナス金利",
                "BOJ", "Fed", "FOMC", "interest rate", "rate hike", "rate cut"},
    "為替": {"円安", "円高", "ドル円", "為替", "USDJPY", "forex", "yen"},
    "米国市場": {"ダウ", "S&P", "ナスダック", "ウォール街", "米株",
                "NYSE", "Wall Street", "Dow", "Nasdaq"},
    "半導体": {"半導体", "GPU", "NVIDIA", "TSMC", "semiconductor", "エヌビディア"},
    "AI": {"AI", "人工知能", "生成AI", "ChatGPT", "LLM", "機械学習"},
    "エネルギー": {"原油", "WTI", "OPEC", "LNG", "石油", "crude oil"},
    "地政学": {"関税", "制裁", "戦争", "tariff", "sanction", "地政学", "紛争"},
}


def classify_theme(title_ja: str | None, title: str | None) -> str:
    """タイトルからテーマを分類する。マッチなしは "その他"。"""
    text = (title_ja or "") + " " + (title or "")
    text_lower = text.lower()

    for theme, keywords in THEMES.items():
        for kw in keywords:
            if kw.lower() in text_lower:
                return theme
    return "その他"


# ── ティッカー抽出 (Phase 24c) ──────────────────────────────────────────

# 4桁銘柄コードのパターン (タイトル中に出現するケース)
_CODE_PATTERN = re.compile(r"\b(\d{4})\b")

# 企業名マッチ用の最小文字数 (短すぎる名前は誤検出する)
_MIN_NAME_LEN = 3


def _build_name_to_code(conn: sqlite3.Connection) -> dict[str, str]:
    """stocks テーブルから企業名 → コードの辞書を構築する。

    名前の長い順にソート済み (最長一致優先)。
    """
    rows = conn.execute("SELECT code, name FROM stocks").fetchall()
    mapping: dict[str, str] = {}
    for code, name in rows:
        if len(name) >= _MIN_NAME_LEN:
            mapping[name] = code
    return dict(sorted(mapping.items(), key=lambda x: len(x[0]), reverse=True))


def extract_tickers_from_title(
    title: str, name_to_code: dict[str, str]
) -> set[str]:
    """タイトルから銘柄コードを抽出する。

    1. 4桁数字のパターンマッチ (ただし stocks テーブルに存在するもののみ)
    2. 企業名の部分一致
    """
    codes: set[str] = set()
    valid_codes = set(name_to_code.values())

    # 4桁コード直接マッチ
    for m in _CODE_PATTERN.finditer(title):
        if m.group(1) in valid_codes:
            codes.add(m.group(1))

    # 企業名マッチ (最長一致優先)
    for name, code in name_to_code.items():
        if name in title:
            codes.add(code)

    return codes


# ── メイン処理 ──────────────────────────────────────────────────────────


def enrich_articles(conn: sqlite3.Connection) -> dict[str, int]:
    """未処理のニュース記事にセンチメント・テーマ・ティッカーを付与する。

    Returns:
        {"sentiment": N, "category": N, "tickers": N} 更新件数。
    """
    counts = {"sentiment": 0, "category": 0, "tickers": 0}

    # --- センチメント (sentiment IS NULL の記事) ---
    rows = conn.execute(
        "SELECT id, title, title_ja FROM news_articles WHERE sentiment IS NULL"
    ).fetchall()
    if rows:
        updates = []
        for row in rows:
            score = analyze_sentiment(row[2], row[1])  # title_ja, title
            updates.append((score, row[0]))
        conn.executemany(
            "UPDATE news_articles SET sentiment = ? WHERE id = ?", updates
        )
        conn.commit()
        counts["sentiment"] = len(updates)
        logger.info(f"センチメント付与: {len(updates)} 件")

    # --- テーマ分類 (category IS NULL の記事) ---
    rows = conn.execute(
        "SELECT id, title, title_ja FROM news_articles WHERE category IS NULL"
    ).fetchall()
    if rows:
        updates = []
        for row in rows:
            theme = classify_theme(row[2], row[1])  # title_ja, title
            updates.append((theme, row[0]))
        conn.executemany(
            "UPDATE news_articles SET category = ? WHERE id = ?", updates
        )
        conn.commit()
        counts["category"] = len(updates)
        logger.info(f"テーマ分類: {len(updates)} 件")

    # --- ティッカー抽出 ---
    # stocks テーブルが存在するか確認
    has_stocks = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='stocks'"
    ).fetchone()
    if not has_stocks:
        logger.info("stocks テーブルなし — ティッカー抽出スキップ")
        return counts

    name_to_code = _build_name_to_code(conn)
    if not name_to_code:
        return counts

    # news_ticker_map に未登録の記事のみ処理
    rows = conn.execute(
        """
        SELECT a.id, a.title, a.title_ja
        FROM news_articles a
        LEFT JOIN news_ticker_map m ON a.id = m.article_id
        WHERE m.article_id IS NULL
        """
    ).fetchall()
    if rows:
        ticker_rows = []
        for row in rows:
            text = row[2] or row[1] or ""  # title_ja or title
            codes = extract_tickers_from_title(text, name_to_code)
            for code in codes:
                ticker_rows.append((row[0], code))
        if ticker_rows:
            conn.executemany(
                "INSERT OR IGNORE INTO news_ticker_map (article_id, ticker) VALUES (?, ?)",
                ticker_rows,
            )
            conn.commit()
            counts["tickers"] = len(ticker_rows)
            logger.info(f"ティッカー紐付け: {len(ticker_rows)} 件")

    return counts
