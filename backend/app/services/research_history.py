from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

import pandas as pd

from app.services.history_policy import RESEARCH_HISTORY_MONTHS, assess_history_coverage


def frame_coverage(frame: pd.DataFrame) -> dict[str, Any]:
    """Describe the actual calendar coverage of one research frame."""
    if frame is None or frame.empty:
        return {
            "start": None,
            "end": None,
            "available_days": 0,
            "available_years": 0.0,
            "status": "insufficient_for_long_horizon_claim",
            "long_horizon_qualified": False,
            "row_count": 0,
        }

    start = pd.Timestamp(frame.index.min()).normalize()
    end = pd.Timestamp(frame.index.max()).normalize()
    available_days = max(0, (end - start).days)
    coverage = assess_history_coverage(available_days=available_days)
    return {
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        **coverage,
        "row_count": int(len(frame)),
    }


def load_research_frames(
    universe: tuple[str, ...],
    *,
    downloader: Callable[..., pd.DataFrame],
    prepare: Callable[[pd.DataFrame], pd.DataFrame],
    research_months: int = RESEARCH_HISTORY_MONTHS,
) -> tuple[dict[str, pd.DataFrame], dict[str, str], dict[str, dict[str, Any]]]:
    """Load research history independently from the interactive chart horizon."""
    frames: dict[str, pd.DataFrame] = {}
    sources: dict[str, str] = {}
    coverage: dict[str, dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=max(1, len(universe))) as executor:
        futures = {
            executor.submit(
                downloader,
                code,
                prefer_official=True,
                update_with_intraday=False,
                official_months=research_months,
            ): code
            for code in universe
        }
        for future in as_completed(futures):
            code = futures[future]
            raw = future.result()
            prepared = prepare(raw)
            frames[code] = prepared
            sources[code] = str(raw.attrs.get("source", "官方交易所資料"))
            coverage[code] = frame_coverage(prepared)

    return frames, sources, coverage


def summarize_universe_coverage(
    universe: tuple[str, ...],
    coverage: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Use the shortest constituent history as the honest universe-level claim."""
    missing = [code for code in universe if code not in coverage]
    if missing:
        raise ValueError("缺少歷史覆蓋資訊：" + "、".join(missing))

    limiting_code = min(
        universe,
        key=lambda code: int(coverage[code].get("available_days", 0)),
    )
    limiting = coverage[limiting_code]
    return {
        "requested_months": RESEARCH_HISTORY_MONTHS,
        "limiting_symbol": limiting_code,
        "actual_start": limiting.get("start"),
        "actual_end": limiting.get("end"),
        "available_days": int(limiting.get("available_days", 0)),
        "available_years": float(limiting.get("available_years", 0.0)),
        "status": limiting.get("status"),
        "long_horizon_qualified": bool(limiting.get("long_horizon_qualified", False)),
        "symbols": coverage,
    }
