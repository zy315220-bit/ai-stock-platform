from __future__ import annotations

import re
from typing import Any


STOCK_CODE_PATTERN = re.compile(
    r"^[0-9][0-9A-Z]{3,5}(?:\.(?:TW|TWO))?$"
)

INVALID_STOCK_CODE_MESSAGE = (
    "股票代號格式不正確，請輸入 4～6 碼台股代號，"
    "例如 2330、0056 或 6488.TWO。"
)


def normalize_stock_code(value: Any) -> str:
    normalized = str(value or "").strip().upper()

    if not normalized:
        raise ValueError("股票代號不能空白。")

    if not STOCK_CODE_PATTERN.fullmatch(normalized):
        raise ValueError(INVALID_STOCK_CODE_MESSAGE)

    return normalized


def base_stock_code(value: Any) -> str:
    normalized = normalize_stock_code(value)

    if normalized.endswith(".TWO"):
        return normalized[:-4]

    if normalized.endswith(".TW"):
        return normalized[:-3]

    return normalized
