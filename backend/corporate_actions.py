"""Corporate-action support for Taiwan ETF historical simulations.

Split normalization is deliberately idempotent: a frame already normalized by
this module must never be adjusted a second time.  This protects every stock or
ETF, including instruments with multiple split/reverse-split events.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from html.parser import HTMLParser
import math
from typing import Any
import pandas as pd
import requests

TWSE_DIVIDEND_URL = "https://www.twse.com.tw/zh/ETFortune-institute/dividendList"
TWSE_0050_SPLIT_SOURCE = "https://www.twse.com.tw/zh/ETFortune/announcement?company=A00005&date=20250617&fund=0050&seq=1&type=all"
REQUEST_TIMEOUT_SECONDS = 15
_HEADERS = {"Accept": "text/html,application/xhtml+xml", "User-Agent": "Mozilla/5.0 (compatible; AI-Stock-Platform/1.0; +https://github.com/zy315220-bit/ai-stock-platform)"}
KNOWN_SPLITS: dict[str, list[dict[str, Any]]] = {"0050": [{"effective_date": "2025-06-18", "ratio": 4.0, "source": TWSE_0050_SPLIT_SOURCE}]}
OFFICIAL_DIVIDEND_FALLBACK: dict[str, tuple[tuple[str, str | None, float], ...]] = {
"0050": (("2020-01-31","2020-03-06",2.9),("2020-07-21","2020-08-24",0.7),("2021-01-22","2021-03-09",3.05),("2021-07-21","2021-08-24",0.35),("2022-01-21","2022-03-04",3.2),("2022-07-18","2022-08-19",1.8),("2023-01-30","2023-03-07",2.6),("2023-07-18","2023-08-11",1.9),("2024-01-17","2024-02-21",3.0),("2024-07-16","2024-08-09",1.0),("2025-01-17","2025-02-20",2.7),("2025-07-21","2025-08-08",0.36),("2026-01-22","2026-02-11",1.0),("2026-07-21","2026-08-10",0.6)),
"0056": (("2020-10-28","2020-12-01",1.6),("2021-10-22","2021-11-25",1.8),("2022-10-19","2022-11-22",2.1),("2023-07-18","2023-08-11",1.0),("2023-10-19","2023-11-14",1.2),("2024-01-17","2024-02-21",0.7),("2024-04-18","2024-05-15",0.79),("2024-07-16","2024-08-09",1.07),("2024-10-17","2024-11-12",1.07),("2025-01-17","2025-02-20",1.07),("2025-04-23","2025-05-14",1.07),("2025-07-21","2025-08-08",0.866),("2025-10-23","2025-11-14",0.866),("2026-01-22","2026-02-11",0.866),("2026-04-23","2026-05-14",1.0),("2026-07-21","2026-08-10",1.35)),
"00878": (("2020-11-17","2020-12-18",0.05),("2021-02-25","2021-03-31",0.15),("2021-05-18","2021-06-21",0.25),("2021-08-17","2021-09-17",0.3),("2021-11-16","2021-12-17",0.28),("2022-02-22","2022-03-28",0.3),("2022-05-18","2022-06-21",0.32),("2022-08-16","2022-09-19",0.28),("2022-11-16","2022-12-19",0.28),("2023-02-16","2023-03-22",0.27),("2023-05-17","2023-06-12",0.27),("2023-08-16","2023-09-11",0.35),("2023-11-16","2023-12-12",0.35),("2024-02-27","2024-03-25",0.4),("2024-05-17","2024-06-13",0.51),("2024-08-16","2024-09-11",0.55),("2024-11-18","2024-12-12",0.55),("2025-02-20","2025-03-18",0.5),("2025-05-19","2025-06-13",0.47),("2025-08-18","2025-09-11",0.4),("2025-11-18","2025-12-12",0.4),("2026-02-26","2026-03-23",0.42),("2026-05-19","2026-06-12",0.66),("2026-08-18","2026-09-11",1.01)),
"00919": (("2023-06-16","2023-07-14",0.54),("2023-09-18","2023-10-17",0.54),("2023-12-18","2024-01-12",0.55),("2024-03-18","2024-04-15",0.66),("2024-06-24","2024-07-15",0.7),("2024-09-23","2024-10-15",0.72),("2024-12-20","2025-01-13",0.72),("2025-03-18","2025-04-15",0.72),("2025-06-17","2025-07-11",0.72),("2025-09-16","2025-10-15",0.54),("2025-12-16","2026-01-13",0.54),("2026-03-17","2026-04-14",0.78),("2026-06-16","2026-07-13",1.0))}

class _TableParser(HTMLParser):
    def __init__(self): super().__init__(); self.rows=[]; self._row=None; self._cell=None
    def handle_starttag(self,tag,attrs):
        if tag=="tr": self._row=[]
        elif tag=="td" and self._row is not None: self._cell=[]
    def handle_data(self,data):
        if self._cell is not None: self._cell.append(data)
    def handle_endtag(self,tag):
        if tag=="td" and self._row is not None and self._cell is not None: self._row.append(" ".join(self._cell).strip()); self._cell=None
        elif tag=="tr" and self._row is not None:
            if self._row: self.rows.append(self._row)
            self._row=None; self._cell=None

def _roc_text_date(value):
    parts=value.strip().replace("年","-").replace("月","-").replace("日","").split("-")
    if len(parts)!=3:return None
    try:
        y,m,d=(int(x) for x in parts); return pd.Timestamp(year=y+1911,month=m,day=d)
    except (TypeError,ValueError): return None

def parse_twse_dividend_html(html,stock_code):
    parser=_TableParser(); parser.feed(html); events=[]
    for row in parser.rows:
        if len(row)<6 or row[0].strip()!=stock_code: continue
        ex=_roc_text_date(row[2]); pay=_roc_text_date(row[4])
        try: amount=float(row[5].replace(",","").strip())
        except ValueError: continue
        if ex is None or amount<=0 or not math.isfinite(amount): continue
        events.append({"ex_date":ex.strftime("%Y-%m-%d"),"payment_date":pay.strftime("%Y-%m-%d") if pay is not None else None,"amount":amount,"source":TWSE_DIVIDEND_URL})
    return sorted(events,key=lambda e:e["ex_date"])

@lru_cache(maxsize=128)
def _download_twse_etf_dividends_cached(stock_code,start_year,end_year):
    r=requests.get(TWSE_DIVIDEND_URL,params={"stkNo":stock_code,"startDate":str(start_year),"endDate":str(end_year)},headers=_HEADERS,timeout=REQUEST_TIMEOUT_SECONDS); r.raise_for_status()
    return tuple((e["ex_date"],e["payment_date"],float(e["amount"])) for e in parse_twse_dividend_html(r.text,stock_code))

def download_twse_etf_dividends(stock_code,*,start,end):
    s=pd.Timestamp(start).normalize(); e=pd.Timestamp(end).normalize()
    try: cached=_download_twse_etf_dividends_cached(stock_code,s.year,e.year)
    except (requests.RequestException,ValueError,TypeError): cached=()
    records=cached or OFFICIAL_DIVIDEND_FALLBACK.get(stock_code,())
    return [{"ex_date":x,"payment_date":p,"amount":a,"source":TWSE_DIVIDEND_URL} for x,p,a in records if s<=pd.Timestamp(x)<=e]

def _inferred_splits(frame):
    if frame.empty or len(frame)<2:return []
    ordered=frame.sort_index(); events=[]
    for pos in range(1,len(ordered)):
        prev=float(ordered.iloc[pos-1]["Close"]); cur=float(ordered.iloc[pos]["Open"])
        if prev<=0 or cur<=0:continue
        observed=prev/cur
        if observed>=1.8: ratio=float(round(observed))
        elif observed<=0.55: ratio=1.0/float(round(1.0/observed))
        else:continue
        if ratio==0 or not(0.05<=ratio<=20) or abs(observed-ratio)/abs(ratio)>0.20:continue
        events.append({"effective_date":pd.Timestamp(ordered.index[pos]).strftime("%Y-%m-%d"),"ratio":ratio,"source":"detected_from_official_ohlcv_discontinuity"})
    return events

def split_events(frame,stock_code):
    known=[dict(e) for e in KNOWN_SPLITS.get(stock_code,[])]; inferred=_inferred_splits(frame); by_date={e["effective_date"]:e for e in inferred}; by_date.update({e["effective_date"]:e for e in known}); return sorted(by_date.values(),key=lambda e:e["effective_date"])

def adjust_dividends_for_splits(dividends,splits):
    out=[]
    for event in dividends:
        amount=float(event["amount"]); ex=pd.Timestamp(event["ex_date"])
        for split in splits:
            if ex<pd.Timestamp(split["effective_date"]): amount/=float(split["ratio"])
        item=dict(event); item["amount"]=amount; out.append(item)
    return out

def apply_split_adjustments(frame,stock_code):
    """Backward-adjust raw OHLCV exactly once to the latest unit basis."""
    if frame is None or frame.empty:return frame
    # Idempotence is critical: stock.py can pass frames through shared pipelines
    # more than once, and callers may reuse already-normalized frames.
    if frame.attrs.get("split_adjusted") is True:
        return frame.copy()
    adjusted=frame.copy(); events=split_events(adjusted,stock_code)
    for event in reversed(events):
        effective=pd.Timestamp(event["effective_date"]); ratio=float(event["ratio"]); mask=adjusted.index<effective
        adjusted.loc[mask,["Open","High","Low","Close"]]/=ratio
        if "Volume" in adjusted.columns: adjusted.loc[mask,"Volume"]*=ratio
    adjusted.attrs.update(frame.attrs); adjusted.attrs["split_adjustments"]=events; adjusted.attrs["price_basis"]="latest-unit split-adjusted"; adjusted.attrs["split_adjusted"]=True
    return adjusted

def attach_official_dividends(frame,stock_code):
    if frame is None or frame.empty:return frame
    output=frame.copy(); dividends=download_twse_etf_dividends(stock_code,start=pd.Timestamp(output.index.min()),end=pd.Timestamp(output.index.max())); splits=list(output.attrs.get("split_adjustments",[])); output.attrs.update(frame.attrs); output.attrs["dividends"]=adjust_dividends_for_splits(dividends,splits); output.attrs["dividend_source"]=TWSE_DIVIDEND_URL; return output

def dividends_by_ex_date(frame):
    totals={}
    for event in frame.attrs.get("dividends",[]):
        ex=str(event.get("ex_date","")); amount=float(event.get("amount",0.0))
        if ex and amount>0:totals[ex]=totals.get(ex,0.0)+amount
    return totals
