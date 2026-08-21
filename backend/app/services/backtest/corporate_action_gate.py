"""Production gate for research/backtest corporate-action integrity.

Keep this adapter small so every backtest/ranking entry point can use the same
fail-closed validation and deterministic dataset-version semantics.
"""
from __future__ import annotations

import pandas as pd

from corporate_action_guard import (
    mark_research_dataset_version,
    validate_research_corporate_actions,
)


def prepare_research_frame(frame: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    """Reject unsafe corporate-action history and stamp its research version."""
    validate_research_corporate_actions(frame, stock_code)
    return mark_research_dataset_version(frame)


def research_metadata(frame: pd.DataFrame) -> dict[str, object]:
    """Metadata that downstream caches/rankings must retain with a result."""
    return {
        "corporate_action_validated": bool(
            frame.attrs.get("corporate_action_validated")
        ),
        "research_dataset_version": frame.attrs.get("research_dataset_version"),
        "price_basis": frame.attrs.get("price_basis"),
        "split_adjustments": list(frame.attrs.get("split_adjustments", [])),
        "dividend_source": frame.attrs.get("dividend_source"),
    }
