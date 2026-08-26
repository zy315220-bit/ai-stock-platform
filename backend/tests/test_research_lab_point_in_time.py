from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.services.research_lab.point_in_time import (
    PointInTimeRecord,
    PointInTimeViolation,
    assert_records_visible,
    visible_records,
)

UTC = timezone.utc


def _record(*, available_hour: int, payload_value: int = 1) -> PointInTimeRecord:
    return PointInTimeRecord.build(
        source="TWSE:test",
        event_at=datetime(2026, 8, 25, 5, 30, tzinfo=UTC),
        available_at=datetime(2026, 8, 25, available_hour, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 8, 26, 1, 0, tzinfo=UTC),
        payload={"value": payload_value},
    )


def test_future_information_is_blocked_fail_closed() -> None:
    record = _record(available_hour=8)
    with pytest.raises(PointInTimeViolation, match="future information blocked"):
        record.assert_available(datetime(2026, 8, 25, 7, 59, tzinfo=UTC))


def test_record_becomes_visible_only_at_publication_timestamp() -> None:
    record = _record(available_hour=8)
    assert not record.is_available(datetime(2026, 8, 25, 7, 59, tzinfo=UTC))
    assert record.is_available(datetime(2026, 8, 25, 8, 0, tzinfo=UTC))


def test_ingestion_time_does_not_rewrite_historical_availability() -> None:
    record = _record(available_hour=8)
    # Data may be downloaded a day later while still being historically usable
    # from the original publication timestamp. This prevents ingestion time from
    # accidentally becoming a source of look-ahead or artificial truncation.
    assert record.ingested_at > record.available_at
    assert record.is_available(datetime(2026, 8, 25, 9, 0, tzinfo=UTC))


def test_visible_records_filters_by_available_at_not_event_at() -> None:
    early = _record(available_hour=7, payload_value=1)
    late = _record(available_hour=9, payload_value=2)
    visible = visible_records(
        [early, late],
        as_of=datetime(2026, 8, 25, 8, 0, tzinfo=UTC),
    )
    assert visible == (early,)


def test_batch_guard_rejects_one_future_record() -> None:
    early = _record(available_hour=7, payload_value=1)
    late = _record(available_hour=9, payload_value=2)
    with pytest.raises(PointInTimeViolation):
        assert_records_visible(
            [early, late],
            as_of=datetime(2026, 8, 25, 8, 0, tzinfo=UTC),
        )


def test_checksum_is_deterministic_and_payload_sensitive() -> None:
    first = _record(available_hour=8, payload_value=1)
    duplicate = _record(available_hour=8, payload_value=1)
    changed = _record(available_hour=8, payload_value=2)
    assert first.checksum == duplicate.checksum
    assert first.checksum != changed.checksum


def test_naive_timestamps_are_rejected() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        PointInTimeRecord.build(
            source="TWSE:test",
            event_at=datetime(2026, 8, 25, 5, 30),
            available_at=datetime(2026, 8, 25, 8, 0, tzinfo=UTC),
            ingested_at=datetime(2026, 8, 26, 1, 0, tzinfo=UTC),
            payload={"value": 1},
        )
