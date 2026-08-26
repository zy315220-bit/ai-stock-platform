from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from typing import Any, Iterable


class PointInTimeViolation(ValueError):
    """Raised when research attempts to consume information not yet available."""


def _aware(value: datetime, *, field: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field} must be timezone-aware")
    return value.astimezone(timezone.utc)


def canonical_payload_checksum(
    *,
    source: str,
    event_at: datetime,
    available_at: datetime,
    payload: dict[str, Any],
) -> str:
    """Return a stable SHA-256 identity for one point-in-time observation."""
    normalized = {
        "source": str(source).strip(),
        "event_at": _aware(event_at, field="event_at").isoformat(),
        "available_at": _aware(available_at, field="available_at").isoformat(),
        "payload": payload,
    }
    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


@dataclass(frozen=True)
class PointInTimeRecord:
    """Immutable research observation with explicit information timing.

    `event_at` describes when the underlying event occurred.
    `available_at` is the earliest timestamp at which a researcher could have
    known the observation. `ingested_at` is audit lineage only and must never be
    substituted for `available_at` when deciding historical eligibility.
    """

    source: str
    event_at: datetime
    available_at: datetime
    ingested_at: datetime
    payload: dict[str, Any]
    checksum: str

    @classmethod
    def build(
        cls,
        *,
        source: str,
        event_at: datetime,
        available_at: datetime,
        ingested_at: datetime,
        payload: dict[str, Any],
    ) -> "PointInTimeRecord":
        normalized_source = str(source).strip()
        if not normalized_source:
            raise ValueError("source is required")
        event_utc = _aware(event_at, field="event_at")
        available_utc = _aware(available_at, field="available_at")
        ingested_utc = _aware(ingested_at, field="ingested_at")
        if available_utc < event_utc:
            raise ValueError("available_at cannot precede event_at")
        if ingested_utc < event_utc:
            raise ValueError("ingested_at cannot precede event_at")
        clean_payload = dict(payload)
        checksum = canonical_payload_checksum(
            source=normalized_source,
            event_at=event_utc,
            available_at=available_utc,
            payload=clean_payload,
        )
        return cls(
            source=normalized_source,
            event_at=event_utc,
            available_at=available_utc,
            ingested_at=ingested_utc,
            payload=clean_payload,
            checksum=checksum,
        )

    def is_available(self, as_of: datetime) -> bool:
        return self.available_at <= _aware(as_of, field="as_of")

    def assert_available(self, as_of: datetime) -> None:
        as_of_utc = _aware(as_of, field="as_of")
        if self.available_at > as_of_utc:
            raise PointInTimeViolation(
                "future information blocked: "
                f"source={self.source}, available_at={self.available_at.isoformat()}, "
                f"research_as_of={as_of_utc.isoformat()}"
            )


def visible_records(
    records: Iterable[PointInTimeRecord],
    *,
    as_of: datetime,
) -> tuple[PointInTimeRecord, ...]:
    """Return only observations that were public by the research timestamp."""
    as_of_utc = _aware(as_of, field="as_of")
    return tuple(record for record in records if record.available_at <= as_of_utc)


def assert_records_visible(
    records: Iterable[PointInTimeRecord],
    *,
    as_of: datetime,
) -> None:
    """Fail closed if any supplied record contains future information."""
    for record in records:
        record.assert_available(as_of)
