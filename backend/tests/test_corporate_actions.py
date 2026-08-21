from __future__ import annotations

import unittest
from unittest.mock import patch
import pandas as pd
from app.services.backtest.benchmark import _calculate_buy_and_hold
from corporate_actions import adjust_dividends_for_splits, apply_split_adjustments, download_twse_etf_dividends, parse_twse_dividend_html

class CorporateActionTests(unittest.TestCase):
    def test_0050_split_removes_non_economic_price_drop(self):
        frame=pd.DataFrame({"Open":[188.0,47.2],"High":[190.0,48.0],"Low":[187.0,46.8],"Close":[188.65,47.16],"Volume":[1_000_000.,4_100_000.]},index=pd.to_datetime(["2025-06-10","2025-06-18"]))
        adjusted=apply_split_adjustments(frame,"0050")
        self.assertAlmostEqual(adjusted.iloc[0]["Close"],47.1625); self.assertEqual(adjusted.iloc[0]["Volume"],4_000_000); self.assertEqual(adjusted.attrs["split_adjustments"][0]["ratio"],4.0)

    def test_0052_seven_for_one_split_is_normalized(self):
        frame=pd.DataFrame({"Open":[238.0,34.2],"High":[242.0,35.0],"Low":[236.0,33.8],"Close":[239.4,34.2],"Volume":[1_000_000.,7_100_000.]},index=pd.to_datetime(["2025-11-25","2025-11-26"]))
        adjusted=apply_split_adjustments(frame,"0052")
        self.assertAlmostEqual(adjusted.iloc[0]["Close"],239.4/7.0)
        self.assertEqual(adjusted.iloc[0]["Volume"],7_000_000)
        self.assertEqual(adjusted.attrs["split_adjustments"][0]["effective_date"],"2025-11-26")
        self.assertEqual(adjusted.attrs["split_adjustments"][0]["ratio"],7.0)

    def test_split_adjustment_is_idempotent(self):
        frame=pd.DataFrame({"Open":[188.,47.2],"High":[190.,48.],"Low":[187.,46.8],"Close":[188.65,47.16],"Volume":[1_000_000.,4_100_000.]},index=pd.to_datetime(["2025-06-10","2025-06-18"]))
        once=apply_split_adjustments(frame,"0050"); twice=apply_split_adjustments(once,"0050"); pd.testing.assert_frame_equal(once,twice)

    def test_multiple_splits_compound_once(self):
        frame=pd.DataFrame({"Open":[400.,205.,70.],"High":[410.,210.,72.],"Low":[390.,200.,68.],"Close":[400.,210.,70.],"Volume":[100.,200.,600.]},index=pd.to_datetime(["2020-01-02","2022-01-03","2024-01-02"]))
        with patch("corporate_actions.KNOWN_SPLITS",{"TEST":[{"effective_date":"2022-01-03","ratio":2.0,"source":"test"},{"effective_date":"2024-01-02","ratio":3.0,"source":"test"}]}):
            adjusted=apply_split_adjustments(frame,"TEST"); self.assertAlmostEqual(adjusted.iloc[0]["Close"],400/6); self.assertAlmostEqual(adjusted.iloc[1]["Close"],210/3); pd.testing.assert_frame_equal(adjusted,apply_split_adjustments(adjusted,"TEST"))

    def test_reverse_split_is_supported(self):
        frame=pd.DataFrame({"Open":[10.,50.],"High":[11.,52.],"Low":[9.,49.],"Close":[10.,50.],"Volume":[500.,100.]},index=pd.to_datetime(["2020-01-02","2022-01-03"]))
        with patch("corporate_actions.KNOWN_SPLITS",{"TEST":[{"effective_date":"2022-01-03","ratio":0.2,"source":"test"}]}):
            adjusted=apply_split_adjustments(frame,"TEST"); self.assertAlmostEqual(adjusted.iloc[0]["Close"],50.0); self.assertAlmostEqual(adjusted.iloc[0]["Volume"],100.0)

    def test_pre_split_dividend_is_normalized_to_latest_unit(self):
        adjusted=adjust_dividends_for_splits([{"ex_date":"2025-01-17","amount":2.7},{"ex_date":"2025-07-21","amount":0.36}],[{"effective_date":"2025-06-18","ratio":4.0}]); self.assertAlmostEqual(adjusted[0]["amount"],0.675); self.assertAlmostEqual(adjusted[1]["amount"],0.36)

    def test_official_dividend_html_parser(self):
        html="""<table><tbody><tr><td>0050</td><td>元大台灣50</td><td>115年07月21日</td><td>115年07月27日</td><td>115年08月10日</td><td>0.6</td></tr></tbody></table>"""; events=parse_twse_dividend_html(html,"0050"); self.assertEqual(events[0]["ex_date"],"2026-07-21"); self.assertEqual(events[0]["amount"],0.6)

    def test_buy_and_hold_total_return_includes_dividends(self):
        frame=pd.DataFrame({"Date":pd.to_datetime(["2025-01-02","2025-07-21","2025-12-31"]),"Open":[10.]*3,"High":[10.]*3,"Low":[10.]*3,"Close":[10.]*3,"Volume":[1000]*3}); frame.attrs["dividends"]=[{"ex_date":"2025-07-21","amount":1.0}]
        result=_calculate_buy_and_hold(frame,initial_capital=10_000,commission_rate=0.,transaction_tax_rate=0.); self.assertEqual(result["return_percent"],10.0); self.assertEqual(result["return_basis"],"split_adjusted_total_return")

    def test_audited_fallback_survives_twse_page_timeout(self):
        with patch("corporate_actions._download_twse_etf_dividends_cached",side_effect=ValueError("timeout")): events=download_twse_etf_dividends("0050",start=pd.Timestamp("2025-01-01"),end=pd.Timestamp("2025-12-31"))
        self.assertEqual([(e["ex_date"],e["amount"]) for e in events],[("2025-01-17",2.7),("2025-07-21",0.36)])

if __name__=="__main__": unittest.main()
