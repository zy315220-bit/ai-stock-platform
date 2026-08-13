from __future__ import annotations

"""
回測模組對外入口。

其他程式建議只從這個檔案匯入 backtest_stock，
不要直接依賴 engine.py 內部細節。
"""

from .engine import (
    MAX_INITIAL_CAPITAL,
    backtest_stock,
)
from .trades import (
    COMMISSION_RATE,
    ETF_TRANSACTION_TAX_RATE,
)

__all__ = [
    "COMMISSION_RATE",
    "ETF_TRANSACTION_TAX_RATE",
    "MAX_INITIAL_CAPITAL",
    "backtest_stock",
]
