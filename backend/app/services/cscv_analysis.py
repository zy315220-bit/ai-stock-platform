from __future__ import annotations

from typing import Any

import pandas as pd

from app.services.cscv_history import build_historical_performance_matrix
from app.services.pbo import calculate_cscv_pbo


def analyze_historical_selection_overfit(
    frames: dict[str, pd.DataFrame],
    *,
    initial_capital: float,
    slice_months: int = 1,
    max_slices: int = 12,
) -> dict[str, Any]:
    """Build real strategy history and immediately evaluate CSCV/PBO."""
    matrix = build_historical_performance_matrix(
        frames,
        initial_capital=initial_capital,
        slice_months=slice_months,
        max_slices=max_slices,
    )
    pbo = calculate_cscv_pbo(matrix)
    return {
        "status": "completed",
        "method": pbo["method"],
        "matrix_schema": matrix["schema"],
        "metric": matrix["metric"],
        "source": matrix["source"],
        "slice_count": matrix["slice_count"],
        "strategy_count": matrix["strategy_count"],
        "slice_months": matrix["slice_months"],
        "market_universe": matrix["market_universe"],
        "cost_model_id": matrix["cost_model_id"],
        "pbo": pbo,
        "matrix": matrix,
        "warning": "此結果是歷史策略選拔的 CSCV/PBO 診斷，不是未來報酬或虧損機率預測。",
    }
