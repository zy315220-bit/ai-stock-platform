from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

import pandas as pd

from app.services import competition_runner as legacy
from app.services.history_policy import RESEARCH_HISTORY_MONTHS
from app.services.research_history import load_research_frames, summarize_universe_coverage


@lru_cache(maxsize=2)
def _load_research_dataset_cached(cache_date: str) -> dict[str, Any]:
    """Download and prepare one shared long-horizon dataset per UTC/local service day.

    Competition, PBO and champion analysis should consume this same object so one
    request path does not download the same 60 months twice.
    """
    from stock import download_stock

    frames, sources, coverage = load_research_frames(
        legacy.COMPETITION_UNIVERSE,
        downloader=download_stock,
        prepare=legacy._prepare_frame,
        research_months=RESEARCH_HISTORY_MONTHS,
    )
    universe_coverage = summarize_universe_coverage(
        legacy.COMPETITION_UNIVERSE,
        coverage,
    )
    return {
        "frames": frames,
        "sources": sources,
        "coverage": coverage,
        "universe_coverage": universe_coverage,
        "requested_months": RESEARCH_HISTORY_MONTHS,
        "cache_date": cache_date,
    }


def load_shared_research_dataset() -> dict[str, Any]:
    """Return the shared daily five-year research dataset."""
    return _load_research_dataset_cached(date.today().isoformat())


def clear_research_dataset_cache() -> None:
    """Test/operations hook for forcing a fresh official-data load."""
    _load_research_dataset_cached.cache_clear()
