from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from app.services.research_lab.official_point_in_time import (
    official_daily_ohlcv_records,
)
from app.services.research_lab.point_in_time import PointInTimeViolation

UTC = timezone.utc


def _frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "Open": [100.0, 101.0],
            "High": [103.0, 104.0],
            "Low": [99.0, 100.0],
            "Close": [102.0, 103.0],
            "Volume": [1_000_000.0, 1_200_000.0],
        },
        index=pd.to_datetime(["2026-08-24", "2026-08-25"]),
    )


def test_official_adapter_requires_publication_time_for_every_day() -> None:
    with pytest.raises(PointInTimeViolation, match="no authoritative publication"):
        official_daily_ohlcv_records(
            _frame(),
            source="TWSE:STOCK_DAY",
            publication_times={
                date(2026, 8, 24): datetime(2026, 8, 24, 7, 0, tzinfo=UTC),
            },
            ingested_at=datetime(2026, 8, 26, 1, 0, tzinfo=UTC),
        )


def test_official_adapter_uses_publication_not_market_date_for_visibility() -> None:
    records = official_daily_ohlcv_records(
        _frame().iloc[[0]],
        source="TWSE:STOCK_DAY",
        publication_times={
            date(2026, 8, 24): datetime(2026, 8, 24, 7, 0, tzinfo=UTC),
        },
        ingested_at=datetime(2026, 8, 26, 1, 0, tzinfo=UTC),
    )
    record = records[0]
    assert record.payload["market_date"] == "2026-08-24"
    assert not record.is_available(datetime(2026, 8, 24, 6, 59, tzinfo=UTC))
    assert record.is_available(datetime(2026, 8, 24, 7, 0, tzinfo=UTC))


def test_publication_before_regular_close_is_rejected() -> None:
    # 05:00 UTC is 13:00 Asia/Taipei, before the default 13:30 close.
    with pytest.raises(ValueError, match="available_at cannot precede event_at"):
        official_daily_ohlcv_records(
            _frame().iloc[[0]],
            source="TWSE:STOCK_DAY",
            publication_times={
                date(2026, 8, 24): datetime(2026, 8, 24, 5, 0, tzinfo=UTC),
            },
            ingested_at=datetime(2026, 8, 26, 1, 0, tzinfo=UTC),
        )


def test_official_adapter_rejects_duplicate_market_dates() -> None:
    frame = _frame().iloc[[0, 0]]
    with pytest.raises(ValueError, match="duplicate market dates"):
        official_daily_ohlcv_records(
            frame,
            source="TWSE:STOCK_DAY",
            publication_times={
                date(2026, 8, 24): datetime(2026, 8, 24, 7, 0, tzinfo=UTC),
            },
            ingested_at=datetime(2026, 8, 26, 1, 0, tzinfo=UTC),
        )


def test_official_adapter_rejects_incomplete_ohlcv_schema() -> None:
    frame = _frame().drop(columns=["Volume"])
    with pytest.raises(ValueError, match="Volume"):
        official_daily_ohlcv_records(
            frame,
            source="TWSE:STOCK_DAY",
            publication_times={},
            ingested_at=datetime(2026, 8, 26, 1, 0, tzinfo=UTC),
        )
