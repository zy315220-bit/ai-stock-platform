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
        return []

    return [
        {
            "ex_date": ex_date,
            "payment_date": payment_date,
            "amount": amount,
            "source": TWSE_DIVIDEND_URL,
        }
        for ex_date, payment_date, amount in cached
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
