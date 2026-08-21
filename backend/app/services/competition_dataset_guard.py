"""Competition dataset integrity/version helpers.

A ranking is only valid for the exact normalized corporate-action datasets that
produced it.  These helpers create a deterministic cross-symbol fingerprint so
corrected split/dividend data cannot silently reuse an older ranking cache/run.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

from app.services.backtest.corporate_action_gate import (
    prepare_research_frame,
    research_metadata,
)


def prepare_competition_frame(frame: pd.DataFrame, stock_code: str) -> pd.DataFrame:
    return prepare_research_frame(frame, stock_code)


def competition_dataset_manifest(frames: dict[str, pd.DataFrame]) -> dict[str, Any]:
    symbols: dict[str, Any] = {}
    for code in sorted(frames):
        meta = research_metadata(frames[code])
        symbols[code] = {
            "research_dataset_version": meta.get("research_dataset_version"),
            "corporate_action_validated": bool(meta.get("corporate_action_validated")),
            "price_basis": meta.get("price_basis"),
            "split_adjustments": meta.get("split_adjustments", []),
            "dividend_source": meta.get("dividend_source"),
        }
    payload = json.dumps(symbols, sort_keys=True, ensure_ascii=False, default=str)
    return {
        "symbols": symbols,
        "fingerprint": hashlib.sha256(payload.encode("utf-8")).hexdigest()[:20],
    }
