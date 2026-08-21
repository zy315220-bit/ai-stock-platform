from __future__ import annotations

import unittest
from unittest.mock import patch
import pandas as pd

from app.services.backtest.engine import _download_backtest_history


class ProductionSplitPipelineTests(unittest.TestCase):
    def _frame(self, code: str) -> pd.DataFrame:
        idx=pd.to_datetime(["2025-01-02","2025-12-31"])
        frame=pd.DataFrame({"Open":[30.,35.],"High":[31.,36.],"Low":[29.,34.],"Close":[30.,35.],"Volume":[1000.,1000.]},index=idx)
        frame.attrs.update({"stock_code":code,"source":"Yahoo Finance","split_adjusted":True,"price_basis":"yahoo_split_adjusted_close","corporate_action_validated":True,"dividends":[]})
        return frame

    @patch("app.services.backtest.engine.download_stock")
    def test_production_history_always_requests_corporate_actions(self, download_stock):
        download_stock.return_value=self._frame("0052")
        result=_download_backtest_history("0052",required_start_date="2025-01-02",required_end_date="2025-12-31")
        self.assertFalse(result.empty)
        self.assertTrue(download_stock.called)
        for call in download_stock.call_args_list:
            self.assertIs(call.kwargs.get("include_corporate_actions"),True)

    @patch("app.services.backtest.engine.download_stock")
    def test_production_history_preserves_split_price_basis(self, download_stock):
        download_stock.return_value=self._frame("0052")
        result=_download_backtest_history("0052",required_start_date="2025-01-02",required_end_date="2025-12-31")
        self.assertIs(result.attrs.get("split_adjusted"),True)
        self.assertEqual(result.attrs.get("price_basis"),"yahoo_split_adjusted_close")


if __name__=="__main__":unittest.main()
