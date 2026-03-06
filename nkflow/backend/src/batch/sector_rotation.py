"""セクターローテーション分析モジュール (Phase 17)

処理フロー:
  1. compute_sector_daily_returns  - 当日セクター日次リターン算出 (初回は全履歴バックフィル)
  2. compute_sector_aggregates     - 週次・月次リターン集計
  3. run_sector_clustering         - K-Means クラスタリング
  4. run_sector_hmm                - HMM レジーム検出 (hmmlearn があれば)
  5. compute_transition_matrix     - 遷移確率行列算出
  6. predict_sector_rotation       - LightGBM 次期状態予測
  7. run_all                       - エントリポイント
"""
import json
import logging
import sqlite3
from datetime import date
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

RANDOM_SEED = 42
N_CLUSTERS = 5
MIN_WEEKS_FOR_CLUSTERING = 12
MIN_WEEKS_FOR_PREDICTION = 52
PREDICTION_TRAIN_RATIO = 0.7

# セクター略称マップ
_SECTOR_ABBR: dict[str, str] = {
    "情報･通信業": "情通",
    "電気機器": "電機",
    "銀行業": "銀行",
    "輸送用機器": "輸送",
    "医薬品": "医薬",
    "食料品": "食品",
    "不動産業": "不動産",
    "化学": "化学",
    "機械": "機械",
    "サービス業": "サービス",
    "小売業": "小売",
    "建設業": "建設",
    "卸売業": "卸売",
    "その他金融業": "その他金融",
    "証券･商品先物取引業": "証券",
    "保険業": "保険",
    "鉄鋼": "鉄鋼",
    "非鉄金属": "非鉄",
    "精密機器": "精密",
    "ガラス･土石製品": "ガラス",
    "繊維製品": "繊維",
    "金属製品": "金属",
    "電気･ガス業": "電ガス",
    "陸運業": "陸運",
    "その他製品": "その他",
    "パルプ・紙": "紙",
    "ゴム製品": "ゴム",
    "倉庫･運輸関連業": "倉庫",
    "水産・農林業": "水産",
    "石油･石炭製品": "石油",
    "海運業": "海運",
    "鉱業": "鉱業",
    "空運業": "空運",
}


def _abbr(sector: str) -> str:
    return _SECTOR_ABBR.get(sector, sector[:4])


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1-1: セクター日次リターン
# ─────────────────────────────────────────────────────────────────────────────

def compute_sector_daily_returns(db_path: str, target_date: str) -> int:
    """当日のセクター別等加重平均リターンを算出して sector_daily_returns に保存する。

    sector_daily_returns テーブルが空の場合は全履歴をバックフィルする。

    Returns:
        保存した行数
    """
    conn = sqlite3.connect(db_path)
    try:
        # 既存データ確認
        existing = conn.execute(
            "SELECT COUNT(*) FROM sector_daily_returns WHERE date = ?", (target_date,)
        ).fetchone()[0]
        if existing > 0:
            logger.info(f"sector_daily_returns: {target_date} は計算済み — スキップ")
            return existing

        # バックフィル判定: テーブルが空なら全日程を処理
        total_rows = conn.execute("SELECT COUNT(*) FROM sector_daily_returns").fetchone()[0]
        if total_rows == 0:
            logger.info("sector_daily_returns: 空のため全履歴をバックフィル")
            dates_to_process = [
                r[0] for r in conn.execute(
                    "SELECT DISTINCT date FROM daily_prices WHERE return_rate IS NOT NULL ORDER BY date"
                ).fetchall()
            ]
        else:
            dates_to_process = [target_date]

        rows_saved = 0
        for dt in dates_to_process:
            df = pd.read_sql(
                """
                SELECT s.sector, AVG(dp.return_rate) AS return_rate, COUNT(*) AS stock_count
                FROM daily_prices dp
                JOIN stocks s ON dp.code = s.code
                WHERE dp.date = ? AND dp.return_rate IS NOT NULL
                GROUP BY s.sector
                """,
                conn,
                params=(dt,),
            )
            if df.empty:
                continue

            df["date"] = dt
            df = df[["date", "sector", "return_rate", "stock_count"]]
            conn.executemany(
                "INSERT OR REPLACE INTO sector_daily_returns (date, sector, return_rate, stock_count) VALUES (?, ?, ?, ?)",
                df.itertuples(index=False, name=None),
            )
            rows_saved += len(df)

        conn.commit()
        logger.info(f"sector_daily_returns 保存: {rows_saved} 行")
        return rows_saved

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 1-3: 週次・月次リターン集計
# ─────────────────────────────────────────────────────────────────────────────

def compute_sector_aggregates(db_path: str) -> tuple[int, int]:
    """sector_daily_returns から週次・月次リターンを再計算して保存する (冪等)。

    週次: 金曜締め (W-FRI)。日次リターンの合計で週間リターンを近似。
    月次: 月末締め (ME)。

    Returns:
        (保存した週次行数, 保存した月次行数)
    """
    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql(
            "SELECT date, sector, return_rate FROM sector_daily_returns ORDER BY date",
            conn,
            parse_dates=["date"],
        )
        if df.empty:
            return 0, 0

        df = df.set_index("date").sort_index()

        # 週次 (W-FRI)
        weekly = (
            df.groupby("sector")["return_rate"]
            .resample("W-FRI")
            .sum()
            .reset_index()
            .rename(columns={"date": "week_date"})
        )
        weekly["week_date"] = weekly["week_date"].dt.strftime("%Y-%m-%d")

        weekly_rows: list[tuple] = []
        for week_date, grp in weekly.groupby("week_date"):
            grp = grp.dropna(subset=["return_rate"])
            grp = grp.sort_values("return_rate", ascending=False).copy()
            grp["rank"] = range(1, len(grp) + 1)
            for _, row in grp.iterrows():
                weekly_rows.append((
                    week_date, row["sector"], float(row["return_rate"]), int(row["rank"])
                ))

        # 月次 (ME)
        monthly = (
            df.groupby("sector")["return_rate"]
            .resample("ME")
            .sum()
            .reset_index()
            .rename(columns={"date": "month_date"})
        )
        monthly["month_date"] = monthly["month_date"].dt.strftime("%Y-%m")

        monthly_rows: list[tuple] = []
        for month_date, grp in monthly.groupby("month_date"):
            grp = grp.dropna(subset=["return_rate"])
            grp = grp.sort_values("return_rate", ascending=False).copy()
            grp["rank"] = range(1, len(grp) + 1)
            for _, row in grp.iterrows():
                monthly_rows.append((
                    month_date, row["sector"], float(row["return_rate"]), int(row["rank"])
                ))

        conn.execute("DELETE FROM sector_weekly_returns")
        conn.executemany(
            "INSERT OR REPLACE INTO sector_weekly_returns (week_date, sector, return_rate, rank) VALUES (?, ?, ?, ?)",
            weekly_rows,
        )

        conn.execute("DELETE FROM sector_monthly_returns")
        conn.executemany(
            "INSERT OR REPLACE INTO sector_monthly_returns (month_date, sector, return_rate, rank) VALUES (?, ?, ?, ?)",
            monthly_rows,
        )

        conn.commit()
        logger.info(f"sector_aggregates: weekly={len(weekly_rows)}, monthly={len(monthly_rows)}")
        return len(weekly_rows), len(monthly_rows)

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2-2: K-Means クラスタリング
# ─────────────────────────────────────────────────────────────────────────────

def _infer_state_name(ret_centroid: np.ndarray, sectors: list[str]) -> str:
    """クラスタ重心の平均リターンベクトルからセクター状態名を推定する。"""
    idx_sorted = np.argsort(ret_centroid)[::-1]
    top1 = _abbr(sectors[idx_sorted[0]])
    top2 = _abbr(sectors[idx_sorted[1]])
    bottom1 = _abbr(sectors[idx_sorted[-1]])
    return f"{top1}・{top2}主導/{bottom1}安"


def _build_top_sectors_json(ret_centroid: np.ndarray, sectors: list[str]) -> str:
    """クラスタ重心から上位5セクターのJSONを返す。"""
    top5_idx = np.argsort(ret_centroid)[::-1][:5]
    return json.dumps(
        [
            {"sector": sectors[int(i)], "avg_return": float(ret_centroid[i])}
            for i in top5_idx
        ],
        ensure_ascii=False,
    )


def run_sector_clustering(db_path: str, n_clusters: int = N_CLUSTERS) -> int:
    """週次セクターリターンランクに K-Means を適用してローテーション状態を保存する。

    特徴量: 各週の全セクター順位ベクトル (33次元)
    クラスタ名: 重心の平均リターンが高い上位2セクターから推定

    Returns:
        保存した状態行数
    """
    try:
        from sklearn.cluster import KMeans
    except ImportError:
        logger.info("scikit-learn が見つかりません — クラスタリングをスキップ")
        return 0

    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql(
            "SELECT week_date, sector, return_rate, rank FROM sector_weekly_returns ORDER BY week_date",
            conn,
        )
        n_weeks = df["week_date"].nunique() if not df.empty else 0
        if df.empty or n_weeks < MIN_WEEKS_FOR_CLUSTERING:
            logger.info(f"sector_clustering: データ不足 ({n_weeks} 週 < {MIN_WEEKS_FOR_CLUSTERING})")
            return 0

        # ピボット: (week_date × sector) の rank 行列 & return_rate 行列
        pivot_rank = df.pivot(index="week_date", columns="sector", values="rank").fillna(0)
        pivot_ret = df.pivot(index="week_date", columns="sector", values="return_rate").fillna(0)

        sectors = list(pivot_rank.columns)
        X_rank = pivot_rank.values.astype(float)

        # K-Means (rank 行列: 全セクター同スケールのため標準化不要)
        km = KMeans(n_clusters=n_clusters, random_state=RANDOM_SEED, n_init=10)
        labels = km.fit_predict(X_rank)

        # 各クラスタの平均リターンを算出 (状態名推定に使用)
        ret_centroids: dict[int, np.ndarray] = {}
        for k in range(n_clusters):
            mask = labels == k
            ret_centroids[k] = pivot_ret.values[mask].mean(axis=0) if mask.any() else np.zeros(len(sectors))

        rows: list[tuple] = []
        for i, week_date in enumerate(pivot_rank.index):
            state_id = int(labels[i])
            state_name = _infer_state_name(ret_centroids[state_id], sectors)
            top_json = _build_top_sectors_json(ret_centroids[state_id], sectors)
            rows.append((week_date, "weekly", "kmeans", state_id, state_name, top_json))

        conn.execute(
            "DELETE FROM sector_rotation_states WHERE period_type='weekly' AND cluster_method='kmeans'"
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO sector_rotation_states
                (period_date, period_type, cluster_method, state_id, state_name, centroid_top_sectors)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        logger.info(f"sector_clustering (kmeans): {len(rows)} 週を {n_clusters} 状態に分類")
        return len(rows)

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 2-3: HMM レジーム検出 (optional)
# ─────────────────────────────────────────────────────────────────────────────

def run_sector_hmm(db_path: str, n_states: int = 4) -> int:
    """GaussianHMM でセクターリターンのレジームを検出する。

    hmmlearn が利用できない場合はスキップする。

    Returns:
        保存した状態行数 (0 = スキップ)
    """
    try:
        from hmmlearn.hmm import GaussianHMM
        from sklearn.preprocessing import StandardScaler
    except ImportError:
        logger.info("hmmlearn が見つかりません — HMM レジーム検出をスキップ")
        return 0

    conn = sqlite3.connect(db_path)
    try:
        df = pd.read_sql(
            "SELECT week_date, sector, return_rate FROM sector_weekly_returns ORDER BY week_date",
            conn,
        )
        n_weeks = df["week_date"].nunique() if not df.empty else 0
        if df.empty or n_weeks < MIN_WEEKS_FOR_CLUSTERING:
            return 0

        pivot = df.pivot(index="week_date", columns="sector", values="return_rate").fillna(0)
        sectors = list(pivot.columns)
        X = pivot.values.astype(float)

        scaler = StandardScaler()
        X_scaled = scaler.fit_transform(X)

        model = GaussianHMM(
            n_components=n_states,
            covariance_type="diag",
            n_iter=100,
            random_state=RANDOM_SEED,
        )
        model.fit(X_scaled)
        labels = model.predict(X_scaled)

        rows: list[tuple] = []
        for i, week_date in enumerate(pivot.index):
            state_id = int(labels[i])
            mask = labels == state_id
            mean_ret = X[mask].mean(axis=0)
            state_name = _infer_state_name(mean_ret, sectors)
            top_json = _build_top_sectors_json(mean_ret, sectors)
            rows.append((week_date, "weekly", "hmm", state_id, state_name, top_json))

        conn.execute(
            "DELETE FROM sector_rotation_states WHERE period_type='weekly' AND cluster_method='hmm'"
        )
        conn.executemany(
            """
            INSERT OR REPLACE INTO sector_rotation_states
                (period_date, period_type, cluster_method, state_id, state_name, centroid_top_sectors)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        logger.info(f"sector_hmm: {len(rows)} 週を {n_states} レジームに分類")
        return len(rows)

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 3-1: 遷移確率行列
# ─────────────────────────────────────────────────────────────────────────────

def compute_transition_matrix(
    db_path: str,
    cluster_method: str = "kmeans",
    n_clusters: int = N_CLUSTERS,
) -> int:
    """クラスタ状態の遷移確率行列を算出して sector_rotation_transitions に保存する。

    P(次の状態=j | 現在の状態=i) を全ペアで計算する。

    Returns:
        保存した遷移エントリ数
    """
    conn = sqlite3.connect(db_path)
    try:
        states = pd.read_sql(
            """
            SELECT period_date, state_id FROM sector_rotation_states
            WHERE period_type='weekly' AND cluster_method=?
            ORDER BY period_date
            """,
            conn,
            params=(cluster_method,),
        )
        if len(states) < 3:
            return 0

        state_seq = states["state_id"].values

        # 遷移カウント行列
        count_matrix = np.zeros((n_clusters, n_clusters), dtype=int)
        for i in range(len(state_seq) - 1):
            frm = int(state_seq[i])
            to = int(state_seq[i + 1])
            if 0 <= frm < n_clusters and 0 <= to < n_clusters:
                count_matrix[frm, to] += 1

        # 確率行列 (行正規化)
        row_sums = count_matrix.sum(axis=1, keepdims=True)
        prob_matrix = np.where(row_sums > 0, count_matrix / row_sums.astype(float), 0.0)

        calc_date = date.today().isoformat()
        rows: list[tuple] = []
        for frm in range(n_clusters):
            for to in range(n_clusters):
                rows.append((
                    frm, to,
                    float(prob_matrix[frm, to]),
                    int(count_matrix[frm, to]),
                    "weekly", cluster_method, calc_date,
                ))

        conn.execute(
            "DELETE FROM sector_rotation_transitions WHERE cluster_method=?",
            (cluster_method,),
        )
        conn.executemany(
            """
            INSERT INTO sector_rotation_transitions
                (from_state, to_state, probability, count, period_type, cluster_method, calc_date)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()
        logger.info(f"transition_matrix ({cluster_method}): {len(rows)} エントリ保存")
        return len(rows)

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Phase 4: LightGBM 予測
# ─────────────────────────────────────────────────────────────────────────────

def _build_feature_matrix(
    pivot_ret: pd.DataFrame,
    pivot_rank: pd.DataFrame,
    states: pd.Series,
    n_states: int,
) -> tuple[np.ndarray, np.ndarray]:
    """予測モデル用の特徴量行列とターゲット配列を構築する。

    特徴量 (1行 = 1週):
      - 過去 1, 4, 8 週の全セクターリターン  (n_sectors × 3)
      - 過去 1 週の全セクター順位             (n_sectors × 1)
      - 現在の状態 (one-hot)                  (n_states)
      - 現在の状態の継続週数                  (1)

    Returns:
        (X: shape (n_samples, n_features), y: shape (n_samples,))
    """
    LAGS = [1, 4, 8]
    weeks = list(pivot_ret.index)
    max_lag = max(LAGS)

    X_list: list[list[float]] = []
    y_list: list[int] = []

    for i in range(max_lag, len(weeks) - 1):
        features: list[float] = []

        # リターン特徴量 (過去 1, 4, 8 週)
        for lag in LAGS:
            w = weeks[i - lag]
            features.extend(pivot_ret.loc[w].values.tolist())

        # 順位特徴量 (直近週)
        features.extend(pivot_rank.loc[weeks[i]].values.tolist())

        # 現在の状態 one-hot
        current_state = int(states.get(weeks[i], -1))
        one_hot = [0.0] * n_states
        if 0 <= current_state < n_states:
            one_hot[current_state] = 1.0
        features.extend(one_hot)

        # 状態継続週数
        duration = 0
        for j in range(i, 0, -1):
            if int(states.get(weeks[j], -1)) == current_state:
                duration += 1
            else:
                break
        features.append(float(duration))

        # ターゲット: 次週の状態
        next_state = int(states.get(weeks[i + 1], -1))
        if next_state < 0:
            continue

        X_list.append(features)
        y_list.append(next_state)

    return np.array(X_list, dtype=float), np.array(y_list, dtype=int)


def predict_sector_rotation(
    db_path: str,
    calc_date: str,
    n_clusters: int = N_CLUSTERS,
) -> dict:
    """LightGBM を使って次期ローテーション状態を予測し DB に保存する。

    ウォークフォワード検証 (70/30 分割) で精度評価後、全データで再学習して予測。

    Returns:
        予測結果 dict (空 dict = データ不足またはライブラリ未インストール)
    """
    try:
        import lightgbm as lgb
    except ImportError:
        logger.info("lightgbm が見つかりません — 状態予測をスキップ")
        return {}

    conn = sqlite3.connect(db_path)
    try:
        wr_df = pd.read_sql(
            "SELECT week_date, sector, return_rate, rank FROM sector_weekly_returns ORDER BY week_date",
            conn,
        )
        states_df = pd.read_sql(
            """
            SELECT period_date, state_id, state_name, centroid_top_sectors
            FROM sector_rotation_states
            WHERE period_type='weekly' AND cluster_method='kmeans'
            ORDER BY period_date
            """,
            conn,
        )

        n_state_weeks = len(states_df)
        if wr_df.empty or n_state_weeks < MIN_WEEKS_FOR_PREDICTION:
            logger.info(f"predict_sector_rotation: データ不足 ({n_state_weeks} 週 < {MIN_WEEKS_FOR_PREDICTION})")
            return {}

        pivot_ret = wr_df.pivot(index="week_date", columns="sector", values="return_rate").fillna(0)
        pivot_rank = wr_df.pivot(index="week_date", columns="sector", values="rank").fillna(0)
        states = states_df.set_index("period_date")["state_id"]

        # 共通インデックスに揃える
        common_weeks = sorted(set(pivot_ret.index) & set(states.index))
        pivot_ret = pivot_ret.loc[common_weeks]
        pivot_rank = pivot_rank.loc[common_weeks]
        states = states.reindex(common_weeks)

        X, y = _build_feature_matrix(pivot_ret, pivot_rank, states, n_clusters)
        if len(X) < 20:
            return {}

        # ウォークフォワード検証 (70/30 分割)
        split = int(len(X) * PREDICTION_TRAIN_RATIO)
        X_train, X_test = X[:split], X[split:]
        y_train, y_test = y[:split], y[split:]

        lgb_params: dict = {
            "objective": "multiclass",
            "num_class": n_clusters,
            "n_estimators": 200,
            "learning_rate": 0.05,
            "num_leaves": 15,
            "random_state": RANDOM_SEED,
            "verbosity": -1,
        }

        model_val = lgb.LGBMClassifier(**lgb_params)
        model_val.fit(X_train, y_train)
        val_acc = float((model_val.predict(X_test) == y_test).mean()) if len(X_test) > 0 else 0.0

        # 全データで再学習
        model_full = lgb.LGBMClassifier(**lgb_params)
        model_full.fit(X, y)

        # 最新の特徴量で予測
        latest_features = X[-1:].reshape(1, -1)
        proba = model_full.predict_proba(latest_features)[0]
        predicted_state_id = int(np.argmax(proba))
        confidence = float(proba[predicted_state_id])

        # 現在の状態情報
        current_state_id = int(states.iloc[-1])
        _cur_rows = states_df[states_df["state_id"] == current_state_id]
        current_state_name = _cur_rows.iloc[-1]["state_name"] if not _cur_rows.empty else "不明"

        _pred_rows = states_df[states_df["state_id"] == predicted_state_id]
        predicted_state_name = _pred_rows.iloc[-1]["state_name"] if not _pred_rows.empty else "不明"

        # 注目セクター (次期状態のトップセクター)
        top_sectors = (
            json.loads(_pred_rows.iloc[-1]["centroid_top_sectors"])
            if not _pred_rows.empty and _pred_rows.iloc[-1]["centroid_top_sectors"]
            else []
        )

        all_proba = []
        for k in range(n_clusters):
            _rows = states_df[states_df["state_id"] == k]
            sname = _rows.iloc[-1]["state_name"] if not _rows.empty else f"状態{k}"
            all_proba.append({
                "state_id": k,
                "state_name": sname,
                "probability": float(proba[k]),
            })

        result = {
            "current_state_id": current_state_id,
            "current_state_name": current_state_name,
            "predicted_state_id": predicted_state_id,
            "predicted_state_name": predicted_state_name,
            "confidence": confidence,
            "top_sectors": top_sectors,
            "all_probabilities": all_proba,
            "model_accuracy": val_acc,
            "calc_date": calc_date,
        }

        conn.execute("DELETE FROM sector_rotation_predictions")
        conn.execute(
            """
            INSERT INTO sector_rotation_predictions
                (calc_date, current_state_id, current_state_name,
                 predicted_state_id, predicted_state_name,
                 confidence, top_sectors, all_probabilities, model_accuracy)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                calc_date,
                current_state_id, current_state_name,
                predicted_state_id, predicted_state_name,
                confidence,
                json.dumps(top_sectors, ensure_ascii=False),
                json.dumps(all_proba, ensure_ascii=False),
                val_acc,
            ),
        )
        conn.commit()

        logger.info(
            f"sector_prediction: {current_state_name} → {predicted_state_name} "
            f"(conf={confidence:.2f}, acc={val_acc:.2f})"
        )
        return result

    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# エントリポイント
# ─────────────────────────────────────────────────────────────────────────────

def run_all(db_path: str, target_date: Optional[str] = None) -> None:
    """セクターローテーション分析の全ステップを実行する。"""
    if target_date is None:
        target_date = date.today().isoformat()

    logger.info(f"=== sector_rotation.run_all 開始: {target_date} ===")

    n_daily = compute_sector_daily_returns(db_path, target_date)
    logger.info(f"sector_daily_returns: {n_daily} 行")

    n_w, n_m = compute_sector_aggregates(db_path)
    logger.info(f"sector_aggregates: weekly={n_w}, monthly={n_m}")

    n_km = run_sector_clustering(db_path)
    logger.info(f"sector_clustering (kmeans): {n_km} 件")

    n_hmm = run_sector_hmm(db_path)
    logger.info(f"sector_hmm: {n_hmm} 件")

    n_t = compute_transition_matrix(db_path)
    logger.info(f"transition_matrix: {n_t} 件")

    pred = predict_sector_rotation(db_path, target_date)
    if pred:
        logger.info(
            f"prediction: {pred.get('current_state_name')} → "
            f"{pred.get('predicted_state_name')} "
            f"(conf={pred.get('confidence', 0):.2f})"
        )

    logger.info("=== sector_rotation.run_all 完了 ===")
