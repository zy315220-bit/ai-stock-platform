"""Corporate-action support for Taiwan ETF historical simulations.

TWSE daily OHLCV reports contain unadjusted market prices.  That is useful for
auditing, but a split creates an artificial price jump in technical indicators
and backtests.  This module normalizes historical prices to the latest unit
basis and attaches official ETF cash-distribution events to the frame.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from html.parser import HTMLParser
import math
from typing import Any

import pandas as pd
import requests


TWSE_DIVIDEND_URL = "https://www.twse.com.tw/zh/ETFortune-institute/dividendList"
TWSE_0050_SPLIT_SOURCE = (
    "https://www.twse.com.tw/zh/ETFortune/announcement"
    "?company=A00005&date=20250617&fund=0050&seq=1&type=all"
)
REQUEST_TIMEOUT_SECONDS = 15

_HEADERS = {
    "Accept": "text/html,application/xhtml+xml",
    "User-Agent": (
        "Mozilla/5.0 (compatible; AI-Stock-Platform/1.0; "
        "+https://github.com/zy315220-bit/ai-stock-platform)"
    ),
}

# Confirmed official events are preferred to inference.  Detection below also
# protects future data from large split/reverse-split discontinuities.
KNOWN_SPLITS: dict[str, list[dict[str, Any]]] = {
    "0050": [
        {
            "effective_date": "2025-06-18",
            "ratio": 4.0,
            "source": TWSE_0050_SPLIT_SOURCE,
        }
    ]
}

# Audited snapshots from TWSE_DIVIDEND_URL.  They keep the core five-year ETF
# backtests deterministic when the public HTML page is slow or temporarily
# blocks a serverless egress address.  A successful live response still wins.
OFFICIAL_DIVIDEND_FALLBACK: dict[
    str, tuple[tuple[str, str | None, float], ...]
] = {
    "0050": (
        ("2020-01-31", "2020-03-06", 2.9),
        ("2020-07-21", "2020-08-24", 0.7),
        ("2021-01-22", "2021-03-09", 3.05),
        ("2021-07-21", "2021-08-24", 0.35),
        ("2022-01-21", "2022-03-04", 3.2),
        ("2022-07-18", "2022-08-19", 1.8),
        ("2023-01-30", "2023-03-07", 2.6),
        ("2023-07-18", "2023-08-11", 1.9),
        ("2024-01-17", "2024-02-21", 3.0),
        ("2024-07-16", "2024-08-09", 1.0),
        ("2025-01-17", "2025-02-20", 2.7),
        ("2025-07-21", "2025-08-08", 0.36),
        ("2026-01-22", "2026-02-11", 1.0),
        ("2026-07-21", "2026-08-10", 0.6),
    ),
    "0056": (
        ("2020-10-28", "2020-12-01", 1.6),
        ("2021-10-22", "2021-11-25", 1.8),
        ("2022-10-19", "2022-11-22", 2.1),
        ("2023-07-18", "2023-08-11", 1.0),
        ("2023-10-19", "2023-11-14", 1.2),
        ("2024-01-17", "2024-02-21", 0.7),
        ("2024-04-18", "2024-05-15", 0.79),
        ("2024-07-16", "2024-08-09", 1.07),
        ("2024-10-17", "2024-11-12", 1.07),
        ("2025-01-17", "2025-02-20", 1.07),
        ("2025-04-23", "2025-05-14", 1.07),
        ("2025-07-21", "2025-08-08", 0.866),
        ("2025-10-23", "2025-11-14", 0.866),
        ("2026-01-22", "2026-02-11", 0.866),
        ("2026-04-23", "2026-05-14", 1.0),
        ("2026-07-21", "2026-08-10", 1.35),
    ),
    "00878": (
        ("2020-11-17", "2020-12-18", 0.05),
        ("2021-02-25", "2021-03-31", 0.15),
        ("2021-05-18", "2021-06-21", 0.25),
        ("2021-08-17", "2021-09-17", 0.3),
        ("2021-11-16", "2021-12-17", 0.28),
        ("2022-02-22", "2022-03-28", 0.3),
        ("2022-05-18", "2022-06-21", 0.32),
        ("2022-08-16", "2022-09-19", 0.28),
        ("2022-11-16", "2022-12-19", 0.28),
        ("2023-02-16", "2023-03-22", 0.27),
        ("2023-05-17", "2023-06-12", 0.27),
        ("2023-08-16", "2023-09-11", 0.35),
        ("2023-11-16", "2023-12-12", 0.35),
        ("2024-02-27", "2024-03-25", 0.4),
        ("2024-05-17", "2024-06-13", 0.51),
        ("2024-08-16", "2024-09-11", 0.55),
        ("2024-11-18", "2024-12-12", 0.55),
        ("2025-02-20", "2025-03-18", 0.5),
        ("2025-05-19", "2025-06-13", 0.47),
        ("2025-08-18", "2025-09-11", 0.4),
        ("2025-11-18", "2025-12-12", 0.4),
        ("2026-02-26", "2026-03-23", 0.42),
        ("2026-05-19", "2026-06-12", 0.66),
        ("2026-08-18", "2026-09-11", 1.01),
    ),
    "00919": (
        ("2023-06-16", "2023-07-14", 0.54),
        ("2023-09-18", "2023-10-17", 0.54),
        ("2023-12-18", "2024-01-12", 0.55),
        ("2024-03-18", "2024-04-15", 0.66),
        ("2024-06-24", "2024-07-15", 0.7),
        ("2024-09-23", "2024-10-15", 0.72),
        ("2024-12-20", "2025-01-13", 0.72),
        ("2025-03-18", "2025-04-15", 0.72),
        ("2025-06-17", "2025-07-11", 0.72),
        ("2025-09-16", "2025-10-15", 0.54),
        ("2025-12-16", "2026-01-13", 0.54),
        ("2026-03-17", "2026-04-14", 0.78),
        ("2026-06-16", "2026-07-13", 1.0),
    ),
}


class _TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        if tag == "tr":
            self._row = []
        elif tag == "td" and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "td" and self._row is not None and self._cell is not None:
            self._row.append(" ".join(self._cell).strip())
            self._cell = None
        elif tag == "tr" and self._row is not None:
            if self._row:
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _roc_text_date(value: str) -> pd.Timestamp | None:
    text = value.strip().replace("年", "-").replace("月", "-").replace("日", "")
    parts = text.split("-")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(part) for part in parts)
        return pd.Timestamp(year=year + 1911, month=month, day=day)
    except (TypeError, ValueError):
        return None


def parse_twse_dividend_html(html: str, stock_code: str) -> list[dict[str, Any]]:
    """Parse official TWSE ETF distribution rows into normalized events."""

    parser = _TableParser()
    parser.feed(html)
    events: list[dict[str, Any]] = []

    for row in parser.rows:
        if len(row) < 6 or row[0].strip() != stock_code:
            continue
        ex_date = _roc_text_date(row[2])
        payment_date = _roc_text_date(row[4])
        try:
            amount = float(row[5].replace(",", "").strip())
        except ValueError:
            continue
        if ex_date is None or amount <= 0 or not math.isfinite(amount):
            continue
        events.append(
            {
                "ex_date": ex_date.strftime("%Y-%m-%d"),
                "payment_date": (
                    payment_date.strftime("%Y-%m-%d") if payment_date is not None else None
                ),
                "amount": amount,
                "source": TWSE_DIVIDEND_URL,
            }
        )

    return sorted(events, key=lambda event: event["ex_date"])


@lru_cache(maxsize=128)
def _download_twse_etf_dividends_cached(
    stock_code: str,
    start_year: int,
    end_year: int,
) -> tuple[tuple[str, str | None, float], ...]:
    response = requests.get(
        TWSE_DIVIDEND_URL,
        params={
            "stkNo": stock_code,
            "startDate": str(start_year),
            "endDate": str(end_year),
        },
        headers=_HEADERS,
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    return tuple(
        (event["ex_date"], event["payment_date"], float(event["amount"]))
        for event in parse_twse_dividend_html(response.text, stock_code)
    )


def download_twse_etf_dividends(
    stock_code: str,
    *,
    start: date | pd.Timestamp,
    end: date | pd.Timestamp,
) -> list[dict[str, Any]]:
    """Return official ETF cash distributions, or an empty list on outage."""

    start_timestamp = pd.Timestamp(start).normalize()
    end_timestamp = pd.Timestamp(end).normalize()
    try:
        cached = _download_twse_etf_dividends_cached(
            stock_code,
            start_timestamp.year,
            end_timestamp.year,
        )
    except (requests.RequestException, ValueError, TypeError):
        cached = ()

    records = cached or OFFICIAL_DIVIDEND_FALLBACK.get(stock_code, ())

    return [
        {
            "ex_date": ex_date,
            "payment_date": payment_date,
            "amount": amount,
            "source": TWSE_DIVIDEND_URL,
        }
        for ex_date, payment_date, amount in records
        if start_timestamp <= pd.Timestamp(ex_date) <= end_timestamp
    ]


def _inferred_splits(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty or len(frame) < 2:
        return []
    ordered = frame.sort_index()
    events: list[dict[str, Any]] = []

    for position in range(1, len(ordered)):
        previous_close = float(ordered.iloc[position - 1]["Close"])
        current_open = float(ordered.iloc[position]["Open"])
        if previous_close <= 0 or current_open <= 0:
            continue
        observed = previous_close / current_open
        if observed >= 1.8:
            ratio = float(round(observed))
        elif observed <= 0.55:
            inverse = 1.0 / observed
            ratio = 1.0 / float(round(inverse))
        else:
            continue
        if ratio == 0 or not (0.05 <= ratio <= 20):
            continue
        # A normal Taiwan session cannot move anywhere near a 2x unit change.
        if abs(observed - ratio) / abs(ratio) > 0.20:
            continue
        events.append(
            {
                "effective_date": pd.Timestamp(ordered.index[position]).strftime("%Y-%m-%d"),
                "ratio": ratio,
                "source": "detected_from_official_ohlcv_discontinuity",
            }
        )
    return events


def split_events(frame: pd.DataFrame, stock_code: str) -> list[dict[str, Any]]:
    known = [dict(event) for event in KNOWN_SPLITS.get(stock_code, [])]
    inferred = _inferred_splits(frame)
    by_date = {event["effective_date"]: event for event in inferred}
    by_date.update({event["effective_date"]: event for event in known})
    return sorted(by_date.values(), key=lambda event: event["effective_date"])


def adjust_dividends_for_splits(
    dividends: list[dict[str, Any]],
    splits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    adjusted: list[dict[str, Any]] = []
    for event in dividends:
        amount = float(event["amount"])
        ex_date = pd.Timestamp(event["ex_date"])
        for split in splits:
            if ex_date < pd.Timestamp(split["effective_date"]):
                amount /= float(split["ratio"])
        normalized = dict(event)
        normalized["amount"] = amount
        adjusted.append(normalized)
    return adjusted


def apply_split_adjustments(frame: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    """Backward-adjust raw OHLCV to the latest unit basis."""

    if frame is None or frame.empty:
        return frame
    adjusted = frame.copy()
    events = split_events(adjusted, stock_code)
    for event in reversed(events):
        effective_date = pd.Timestamp(event["effective_date"])
        ratio = float(event["ratio"])
        mask = adjusted.index < effective_date
        adjusted.loc[mask, ["Open", "High", "Low", "Close"]] /= ratio
        if "Volume" in adjusted.columns:
            adjusted.loc[mask, "Volume"] *= ratio
    adjusted.attrs.update(frame.attrs)
    adjusted.attrs["split_adjustments"] = events
    adjusted.attrs["price_basis"] = "latest-unit split-adjusted"
    return adjusted


def attach_official_dividends(frame: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    if frame is None or frame.empty:
        return frame
    output = frame.copy()
    dividends = download_twse_etf_dividends(
        stock_code,
        start=pd.Timestamp(output.index.min()),
        end=pd.Timestamp(output.index.max()),
    )
    splits = list(output.attrs.get("split_adjustments", []))
    output.attrs.update(frame.attrs)
    output.attrs["dividends"] = adjust_dividends_for_splits(dividends, splits)
    output.attrs["dividend_source"] = TWSE_DIVIDEND_URL
    return output


def dividends_by_ex_date(frame: pd.DataFrame) -> dict[str, float]:
    totals: dict[str, float] = {}
    for event in frame.attrs.get("dividends", []):
        ex_date = str(event.get("ex_date", ""))
        amount = float(event.get("amount", 0.0))
        if ex_date and amount > 0:
            totals[ex_date] = totals.get(ex_date, 0.0) + amount
    return totals
