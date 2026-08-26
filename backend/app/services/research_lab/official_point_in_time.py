from __future__ import annotations

from datetime import date, datetime, time
from typing import Mapping
from zoneinfo import ZoneInfo

import pandas as pd

from .point_in_time import PointInTimeRecord, PointInTimeViolation

TAIPEI = ZoneInfo("Asia/Taipei")
_REQUIRED_OHLCV = ("Open", "High", "Low", "Close", "Volume")


def _market_date(value: object) -> date:
    timestamp = pd.Timestamp(value)
    if pd.isna(timestamp):
        raise ValueError("daily bar index contains an invalid date")
    return timestamp.date()


def _publication_lookup(
    publication_times: Mapping[date, datetime],
    market_date: date,
) -> datetime:
    published_at = publication_times.get(market_date)
    if published_at is None:
        raise PointInTimeViolation(
            "official observation has no authoritative publication timestamp: "
            f"market_date={market_date.isoformat()}"
        )
    return published_at


def official_daily_ohlcv_records(
    frame: pd.DataFrame,
    *,
    source: str,
    publication_times: Mapping[date, datetime],
    ingested_at: datetime,
    market_timezone: ZoneInfo = TAIPEI,
    regular_close: time = time(13, 30),
) -> tuple[PointInTimeRecord, ...]:
    """Convert official daily OHLCV into auditable point-in-time records.

    Publication time is intentionally mandatory. The adapter never infers that
    a row was knowable merely because its market date is in the past. This
    prevents exchange reports, revised data and late publications from leaking
    into a historical research timestamp.
    """
    missing_columns = [column for column in _REQUIRED_OHLCV if column not in frame]
    if missing_columns:
        raise ValueError(
            "official OHLCV frame missing required columns: "
            + ", ".join(missing_columns)
        )
    if frame.index.has_duplicates:
        raise ValueError("official OHLCV frame contains duplicate market dates")

    records: list[PointInTimeRecord] = []
    for index, row in frame.sort_index().iterrows():
        market_date = _market_date(index)
        event_at = datetime.combine(
            market_date,
            regular_close,
            tzinfo=market_timezone,
        )
        available_at = _publication_lookup(publication_times, market_date)
        payload = {
            "market_date": market_date.isoformat(),
            "open": float(row["Open"]),
            "high": float(row["High"]),
            "low": float(row["Low"]),
            "close": float(row["Close"]),
            "volume": float(row["Volume"]),
        }
        records.append(
            PointInTimeRecord.build(
                source=source,
                event_at=event_at,
                available_at=available_at,
                ingested_at=ingested_at,
                payload=payload,
            )
        )
    return tuple(records)
