from __future__ import annotations

import unittest

from app.services.trading_costs import (
    TAIWAN_ETF_COST_MODEL,
    TAIWAN_STOCK_COST_MODEL,
    buy_cost,
    cost_model_for,
    sell_value,
)


class TradingCostModelTests(unittest.TestCase):
    def test_stock_and_etf_have_distinct_transaction_tax_rates(self) -> None:
        self.assertEqual(TAIWAN_STOCK_COST_MODEL.transaction_tax_rate, 0.003)
        self.assertEqual(TAIWAN_ETF_COST_MODEL.transaction_tax_rate, 0.001)
        self.assertEqual(cost_model_for("stock"), TAIWAN_STOCK_COST_MODEL)
        self.assertEqual(cost_model_for("etf"), TAIWAN_ETF_COST_MODEL)

    def test_buy_cost_charges_commission_but_no_transaction_tax(self) -> None:
        result = buy_cost(price=100.0, shares=1000, model=TAIWAN_STOCK_COST_MODEL)
        self.assertAlmostEqual(result["gross_amount"], 100_000.0)
        self.assertAlmostEqual(result["commission"], 142.5)
        self.assertAlmostEqual(result["total_cost"], 100_142.5)

    def test_sell_value_uses_instrument_specific_tax(self) -> None:
        stock = sell_value(price=100.0, shares=1000, model=TAIWAN_STOCK_COST_MODEL)
        etf = sell_value(price=100.0, shares=1000, model=TAIWAN_ETF_COST_MODEL)
        self.assertAlmostEqual(stock["transaction_tax"], 300.0)
        self.assertAlmostEqual(etf["transaction_tax"], 100.0)
        self.assertAlmostEqual(stock["commission"], etf["commission"])
        self.assertLess(stock["net_amount"], etf["net_amount"])

    def test_negative_inputs_are_rejected(self) -> None:
        with self.assertRaises(ValueError):
            buy_cost(price=-1.0, shares=1, model=TAIWAN_ETF_COST_MODEL)
        with self.assertRaises(ValueError):
            sell_value(price=1.0, shares=-1, model=TAIWAN_ETF_COST_MODEL)


if __name__ == "__main__":
    unittest.main()
