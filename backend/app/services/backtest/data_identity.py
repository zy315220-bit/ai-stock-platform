"""Version the economic inputs of a fixed research window, not feed labels."""
from __future__ import annotations

from dataclasses import asdict
from hashlib import sha256
import json

import pandas as pd

from .corporate_action_adapter import ledger_schedule_from_frame


ECONOMIC_FRAME_SCHEMA = "economic-research-frame-v1"
_INPUT_COLUMNS = (
    "Open", "High", "Low", "Close", "Volume",
    "MA5", "MA20", "MA60", "EMA5", "EMA20", "EMA60",
    "EMA20Slope", "EMA60Slope", "RSI", "MACD", "Signal", "MACD_Hist",
    "K", "D", "Upper", "Lower", "BBWidth", "TR", "ATR", "ATRPercent",
    "NATR", "PlusDI", "MinusDI", "ADX", "VMA20", "VolumeRatio",
    "VolumeChange", "PriceChange", "PriceChangePercent",
)


def economic_frame_identity(stock_code: str, frame: pd.DataFrame) -> dict[str, str]:
    """Hash causal prices/indicators and the cash/share events actually in-window.

    The execution gate has already validated provenance. A provider URL, an
    announcement label, or a dividend after this window cannot change its
    simulated cash flows. Real price, warm-up-indicator, or cash-flow revisions
    still invalidate the identity. The unmodified provenance fingerprint stays
    in score_series_cache for audit and verified legacy-memory migration.
    """
    dates = pd.to_datetime(frame["Date"]).dt.strftime("%Y-%m-%d")
    if frame.empty or dates.isna().any():
        raise ValueError("Economic research identity requires dated observations")
    columns = [column for column in _INPUT_COLUMNS if column in frame]
    inputs = frame[columns].astype(float).copy()
    inputs.insert(0, "Date", dates)
    digest = sha256()
    digest.update(ECONOMIC_FRAME_SCHEMA.encode())
    digest.update(stock_code.encode())
    digest.update(json.dumps(list(inputs.columns)).encode())
    digest.update(pd.util.hash_pandas_object(inputs, index=False).to_numpy().tobytes())
    start, end = str(dates.min()), str(dates.max())
    events = []
    for effective_date, dated_events in ledger_schedule_from_frame(frame).items():
        if not start <= effective_date <= end:
            continue
        for event in dated_events:
            economic = asdict(event)
            economic.pop("source", None)
            economic.pop("announce_date", None)
            events.append(economic)
    # Keep multiplicity and within-date order: both can affect accounting.
    events.sort(key=lambda event: event["effective_date"])
    digest.update(json.dumps(events, sort_keys=True, separators=(",", ":")).encode())
    return {"schema": ECONOMIC_FRAME_SCHEMA, "fingerprint": digest.hexdigest()}
