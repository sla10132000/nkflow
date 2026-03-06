"""GET /api/sector-rotation/* エンドポイント (Phase 17)"""
import logging
from sqlite3 import Connection

from fastapi import APIRouter, Depends, HTTPException

from src.api.helpers import safe_json_loads
from src.api.storage import get_connection

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sector-rotation/performance")
def get_sector_performance(
    period: str = "1d",
    conn: Connection = Depends(get_connection),
):
    """日本セクター騰落率を期間別に返す。

    period: '1d' | '1w' | '1m' | '3m'
    Returns: [{ sector, avg_return }]
    """
    if period == "1d":
        rows = conn.execute(
            """
            SELECT sector, return_rate
            FROM sector_daily_returns
            WHERE date = (SELECT MAX(date) FROM sector_daily_returns)
            ORDER BY sector
            """,
        ).fetchall()
    elif period == "1w":
        rows = conn.execute(
            """
            SELECT sector, return_rate
            FROM sector_weekly_returns
            WHERE week_date = (SELECT MAX(week_date) FROM sector_weekly_returns)
            ORDER BY sector
            """,
        ).fetchall()
    elif period == "1m":
        rows = conn.execute(
            """
            SELECT sector, return_rate
            FROM sector_monthly_returns
            WHERE month_date = (SELECT MAX(month_date) FROM sector_monthly_returns)
            ORDER BY sector
            """,
        ).fetchall()
    elif period == "3m":
        rows = conn.execute(
            """
            SELECT sector, SUM(return_rate) AS return_rate
            FROM sector_monthly_returns
            WHERE month_date IN (
                SELECT DISTINCT month_date FROM sector_monthly_returns
                ORDER BY month_date DESC LIMIT 3
            )
            GROUP BY sector
            ORDER BY sector
            """,
        ).fetchall()
    else:
        raise HTTPException(status_code=400, detail=f"不明な period: {period}")

    # sector_daily_returns にデータがない場合は summary の sector_rotation にフォールバック
    if not rows and period == "1d":
        row = conn.execute(
            "SELECT sector_rotation FROM daily_summary ORDER BY date DESC LIMIT 1"
        ).fetchone()
        if row and row[0]:
            data = safe_json_loads(row[0])
            if data:
                return [
                    {"sector": d["sector"], "avg_return": d.get("avg_return", 0)}
                    for d in data
                    if "sector" in d
                ]

    return [{"sector": r[0], "avg_return": r[1] or 0} for r in rows]


@router.get("/sector-rotation/heatmap")
def get_sector_rotation_heatmap(
    periods: int = 12,
    period_type: str = "weekly",
    conn: Connection = Depends(get_connection),
):
    """セクター別リターンのヒートマップデータを返す。

    period_type: 'weekly' | 'monthly'
    periods: 取得する期間数 (デフォルト12)
    """
    if period_type == "weekly":
        rows = conn.execute(
            """
            SELECT week_date AS period, sector, return_rate, rank
            FROM sector_weekly_returns
            WHERE week_date IN (
                SELECT DISTINCT week_date FROM sector_weekly_returns
                ORDER BY week_date DESC LIMIT ?
            )
            ORDER BY week_date ASC, sector
            """,
            (periods,),
        ).fetchall()
    elif period_type == "monthly":
        rows = conn.execute(
            """
            SELECT month_date AS period, sector, return_rate, rank
            FROM sector_monthly_returns
            WHERE month_date IN (
                SELECT DISTINCT month_date FROM sector_monthly_returns
                ORDER BY month_date DESC LIMIT ?
            )
            ORDER BY month_date ASC, sector
            """,
            (periods,),
        ).fetchall()
    else:
        raise HTTPException(status_code=400, detail=f"不明な period_type: {period_type}")

    if not rows:
        return {"periods": [], "sectors": [], "data": []}

    all_periods = sorted(set(r[0] for r in rows))
    all_sectors = sorted(set(r[1] for r in rows))

    return {
        "periods": all_periods,
        "sectors": all_sectors,
        "data": [
            {"period": r[0], "sector": r[1], "return_rate": r[2], "rank": r[3]}
            for r in rows
        ],
    }


@router.get("/sector-rotation/states")
def get_sector_rotation_states(
    cluster_method: str = "kmeans",
    limit: int = 52,
    conn: Connection = Depends(get_connection),
):
    """ローテーション状態の時系列を返す (新しい順→古い順に並べ直し)。"""
    rows = conn.execute(
        """
        SELECT period_date, state_id, state_name, centroid_top_sectors
        FROM sector_rotation_states
        WHERE period_type='weekly' AND cluster_method=?
        ORDER BY period_date DESC
        LIMIT ?
        """,
        (cluster_method, limit),
    ).fetchall()

    return {
        "states": [
            {
                "period": r[0],
                "state_id": r[1],
                "state_name": r[2],
                "top_sectors": safe_json_loads(r[3], default=[]),
            }
            for r in reversed(rows)
        ]
    }


@router.get("/sector-rotation/transitions")
def get_sector_rotation_transitions(
    cluster_method: str = "kmeans",
    conn: Connection = Depends(get_connection),
):
    """遷移確率行列と各状態名を返す。"""
    trans_rows = conn.execute(
        """
        SELECT from_state, to_state, probability, count
        FROM sector_rotation_transitions
        WHERE cluster_method=?
        ORDER BY from_state, to_state
        """,
        (cluster_method,),
    ).fetchall()

    # 各状態の代表名を取得 (最新のラベル)
    name_rows = conn.execute(
        """
        SELECT state_id, state_name
        FROM sector_rotation_states
        WHERE cluster_method=?
        GROUP BY state_id
        HAVING MAX(period_date)
        ORDER BY state_id
        """,
        (cluster_method,),
    ).fetchall()
    state_names = {r[0]: r[1] for r in name_rows}

    # 各状態の自己遷移確率 (継続しやすさ)
    avg_duration_rows = conn.execute(
        """
        WITH runs AS (
            SELECT period_date, state_id,
                   state_id != LAG(state_id) OVER (ORDER BY period_date) AS is_new_run
            FROM sector_rotation_states
            WHERE period_type='weekly' AND cluster_method=?
        ),
        run_ids AS (
            SELECT period_date, state_id,
                   SUM(CASE WHEN is_new_run THEN 1 ELSE 0 END) OVER (ORDER BY period_date) AS run_id
            FROM runs
        )
        SELECT state_id, AVG(run_len) AS avg_duration
        FROM (
            SELECT state_id, COUNT(*) AS run_len FROM run_ids GROUP BY run_id, state_id
        )
        GROUP BY state_id
        """,
        (cluster_method,),
    ).fetchall()
    avg_durations = {r[0]: round(float(r[1]), 1) for r in avg_duration_rows}

    return {
        "transitions": [
            {
                "from_state": r[0],
                "to_state": r[1],
                "probability": round(float(r[2]), 3),
                "count": r[3],
            }
            for r in trans_rows
        ],
        "state_names": state_names,
        "avg_durations": avg_durations,
    }


@router.get("/sector-rotation/prediction")
def get_sector_rotation_prediction(
    conn: Connection = Depends(get_connection),
):
    """最新のローテーション状態予測を返す。"""
    row = conn.execute(
        """
        SELECT calc_date, current_state_id, current_state_name,
               predicted_state_id, predicted_state_name,
               confidence, top_sectors, all_probabilities, model_accuracy
        FROM sector_rotation_predictions
        ORDER BY calc_date DESC
        LIMIT 1
        """,
    ).fetchone()

    if not row:
        return {"available": False}

    return {
        "available": True,
        "calc_date": row[0],
        "current": {
            "state_id": row[1],
            "state_name": row[2],
        },
        "prediction": {
            "state_id": row[3],
            "state_name": row[4],
            "confidence": row[5],
        },
        "top_sectors": safe_json_loads(row[6], default=[]),
        "all_probabilities": safe_json_loads(row[7], default=[]),
        "model_accuracy": row[8],
    }
