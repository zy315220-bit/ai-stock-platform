from __future__ import annotations

"""
舊匯入路徑相容層。

原本程式：
    from app.services.backtest_service import backtest_stock

可繼續使用。
"""

from .backtest import (
    COMMISSION_RATE,
    ETF_TRANSACTION_TAX_RATE,
    MAX_INITIAL_CAPITAL,
    backtest_stock,
)

__all__ = [
    "COMMISSION_RATE",
    "ETF_TRANSACTION_TAX_RATE",
    "MAX_INITIAL_CAPITAL",
    "backtest_stock",
]
