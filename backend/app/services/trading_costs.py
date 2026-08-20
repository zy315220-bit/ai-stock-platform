from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

InstrumentType = Literal["stock", "etf"]

DEFAULT_COMMISSION_RATE = 0.001425
STOCK_TRANSACTION_TAX_RATE = 0.003
ETF_TRANSACTION_TAX_RATE = 0.001


@dataclass(frozen=True)
class TradingCostModel:
    model_id: str
    instrument_type: InstrumentType
    commission_rate: float
    transaction_tax_rate: float


TAIWAN_STOCK_COST_MODEL = TradingCostModel(
    model_id="TW-STOCK-0.1425-0.3-v1",
    instrument_type="stock",
    commission_rate=DEFAULT_COMMISSION_RATE,
    transaction_tax_rate=STOCK_TRANSACTION_TAX_RATE,
)

TAIWAN_ETF_COST_MODEL = TradingCostModel(
    model_id="TW-ETF-0.1425-0.1-v1",
    instrument_type="etf",
    commission_rate=DEFAULT_COMMISSION_RATE,
    transaction_tax_rate=ETF_TRANSACTION_TAX_RATE,
)


def cost_model_for(instrument_type: InstrumentType) -> TradingCostModel:
    if instrument_type == "stock":
        return TAIWAN_STOCK_COST_MODEL
    if instrument_type == "etf":
        return TAIWAN_ETF_COST_MODEL
    raise ValueError(f"Unsupported instrument type: {instrument_type}")


def buy_cost(*, price: float, shares: int, model: TradingCostModel) -> dict[str, float]:
    if price < 0 or shares < 0:
        raise ValueError("price and shares must be non-negative")
    gross_amount = price * shares
    commission = gross_amount * model.commission_rate
    return {
        "gross_amount": gross_amount,
        "commission": commission,
        "total_cost": gross_amount + commission,
    }


def sell_value(*, price: float, shares: int, model: TradingCostModel) -> dict[str, float]:
    if price < 0 or shares < 0:
        raise ValueError("price and shares must be non-negative")
    gross_amount = price * shares
    commission = gross_amount * model.commission_rate
    transaction_tax = gross_amount * model.transaction_tax_rate
    return {
        "gross_amount": gross_amount,
        "commission": commission,
        "transaction_tax": transaction_tax,
        "net_amount": gross_amount - commission - transaction_tax,
    }
