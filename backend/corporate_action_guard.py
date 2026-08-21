"""Fail-closed research guard for corporate actions not yet normalized.

The simulator must never silently treat a structural price/share change as
alpha.  This guard is deliberately generic: split/reverse split, capital
reduction, stock dividend/rights, merger/share exchange and delisting/suspension
can all create discontinuities or missing regimes. Known normalized events are
allowed; unresolved structural breaks block research/ranking.
"""
from __future__ import annotations
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


def mark_research_dataset_version(frame: pd.DataFrame) -> pd.DataFrame:
    """Attach a deterministic version key so corrected datasets can invalidate caches."""
    output = frame.copy()
    attrs = dict(frame.attrs)
    events = attrs.get("split_adjustments", [])
    dividends = attrs.get("dividends", [])
    signature = (
        str(attrs.get("price_basis", "")),
        tuple(sorted((str(e.get("effective_date", "")), str(e.get("adjustment_date", "")), float(e.get("ratio", 0))) for e in events)),
        tuple(sorted((str(e.get("ex_date", "")), float(e.get("amount", 0))) for e in dividends)),
    )
    attrs["research_dataset_version"] = repr(signature)
    output.attrs.update(attrs)
    return output
