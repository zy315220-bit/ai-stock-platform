"""Fail-closed research guard for corporate actions not yet normalized.

The simulator must never silently treat a structural price/share change as
alpha.  This guard is deliberately generic: split/reverse split, capital
reduction, stock dividend/rights, merger/share exchange and delisting/suspension
can all create discontinuities or missing regimes. Known normalized events are
allowed; unresolved structural breaks block research/ranking.
"""
from __future__ import annotations
from dataclasses import asdict, is_dataclass
from enum import Enum
import hashlib
import json
import math
import pandas as pd

STRUCTURAL_BREAK_LOW = 0.55
STRUCTURAL_BREAK_HIGH = 1.80


def validate_research_corporate_actions(frame: pd.DataFrame, stock_code: str) -> None:
    if frame is None or frame.empty:
        raise ValueError(f"{stock_code} 沒有可驗證的研究價格資料。")
    if not bool(frame.attrs.get("corporate_action_validated")):
        raise ValueError(
            f"{stock_code} corporate-action basis 尚未驗證；拒絕進入回測與排名。"
        )
    ordered = frame.sort_index()
    if len(ordered) < 2:
        return
    allowed_dates = set()
    for event in frame.attrs.get("split_adjustments", []):
        for key in ("effective_date", "adjustment_date"):
            value = event.get(key)
            if value:
                allowed_dates.add(pd.Timestamp(value).normalize())
    unresolved = []
    for pos in range(1, len(ordered)):
        prev = float(ordered.iloc[pos - 1]["Close"])
        cur = float(ordered.iloc[pos]["Open"])
        if prev <= 0 or cur <= 0 or not math.isfinite(prev) or not math.isfinite(cur):
            continue
        ratio = prev / cur
        if STRUCTURAL_BREAK_LOW < ratio < STRUCTURAL_BREAK_HIGH:
            continue
        date = pd.Timestamp(ordered.index[pos]).normalize()
        if date in allowed_dates:
            continue
        unresolved.append((date.strftime("%Y-%m-%d"), ratio))
    if unresolved:
        date, ratio = unresolved[0]
        raise ValueError(
            f"{stock_code} 在 {date} 有未解釋的結構性價格/股本跳變（約 {ratio:.4f} 倍）。"
            "可能涉及減資、除權/股票股利、合併換股、拆併股或資料缺口；"
            "為避免污染研究成果，本次回測與排名已停止。"
        )


def _canonical(value):
    if is_dataclass(value):
        return _canonical(asdict(value))
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {
            str(key): _canonical(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple, set)):
        return [_canonical(item) for item in value]
    if isinstance(value, pd.Timestamp):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _ohlcv_digest(frame: pd.DataFrame) -> str:
    columns = [
        column
        for column in ("Open", "High", "Low", "Close", "Volume")
        if column in frame.columns
    ]
    normalized = frame.loc[:, columns].copy().sort_index()
    normalized.index = pd.to_datetime(normalized.index).strftime("%Y-%m-%dT%H:%M:%S")
    row_hashes = pd.util.hash_pandas_object(
        normalized,
        index=True,
        categorize=False,
    )
    return hashlib.sha256(row_hashes.values.tobytes()).hexdigest()


def mark_research_dataset_version(frame: pd.DataFrame) -> pd.DataFrame:
    """Hash prices and every normalized event so any correction invalidates rankings."""
    output = frame.copy()
    attrs = dict(frame.attrs)
    start = pd.Timestamp(frame.index.min()).strftime("%Y-%m-%d")
    end = pd.Timestamp(frame.index.max()).strftime("%Y-%m-%d")
    manifest = {
        "schema_version": "research-dataset-v2",
        "stock_code": attrs.get("stock_code"),
        "source": attrs.get("source"),
        "price_basis": attrs.get("price_basis"),
        "start": start,
        "end": end,
        "row_count": int(len(frame)),
        "ohlcv_sha256": _ohlcv_digest(frame),
        "split_adjustments": _canonical(attrs.get("split_adjustments", [])),
        "dividends": _canonical(attrs.get("dividends", [])),
        "dividend_source": attrs.get("dividend_source"),
        "corporate_action_events": _canonical(
            attrs.get("corporate_action_events", [])
        ),
        "corporate_action_resolutions": _canonical(
            attrs.get("corporate_action_resolutions", [])
        ),
        "corporate_action_catalog_revision": attrs.get(
            "corporate_action_catalog_revision"
        ),
    }
    payload = json.dumps(
        manifest,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    attrs["research_dataset_manifest"] = manifest
    attrs["research_dataset_version"] = hashlib.sha256(
        payload.encode("utf-8")
    ).hexdigest()
    output.attrs.update(attrs)
    return output
