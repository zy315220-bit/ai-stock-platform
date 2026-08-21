from __future__ import annotations

import pandas as pd

from .models import ResearchSplit


def build_research_split(
    start_date: str,
    end_date: str,
    train_fraction: float = 0.60,
    validation_fraction: float = 0.20,
) -> ResearchSplit:
    """Create chronological train/validation/holdout boundaries.

    The final segment is an untouched holdout. Candidate generation and tuning
    must never use holdout results. Splits are chronological, never shuffled.
    """
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    if start >= end:
        raise ValueError("start_date must be earlier than end_date")
    if not 0 < train_fraction < 1:
        raise ValueError("train_fraction must be between 0 and 1")
    if not 0 < validation_fraction < 1:
        raise ValueError("validation_fraction must be between 0 and 1")
    if train_fraction + validation_fraction >= 1:
        raise ValueError("train + validation must leave an untouched holdout")

    days = (end - start).days
    train_end = start + pd.Timedelta(days=max(1, int(days * train_fraction)))
    validation_start = train_end + pd.Timedelta(days=1)
    validation_end = start + pd.Timedelta(
        days=max(2, int(days * (train_fraction + validation_fraction)))
    )
    holdout_start = validation_end + pd.Timedelta(days=1)

    if holdout_start > end:
        raise ValueError("date range is too short to create all research splits")

    fmt = lambda value: value.strftime("%Y-%m-%d")
    return ResearchSplit(
        train_start=fmt(start),
        train_end=fmt(train_end),
        validation_start=fmt(validation_start),
        validation_end=fmt(validation_end),
        holdout_start=fmt(holdout_start),
        holdout_end=fmt(end),
    )
