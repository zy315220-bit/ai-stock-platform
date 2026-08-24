"""Corporate-action support for Taiwan ETF historical simulations.

Known TWSE split metadata remains authoritative, while provider-specific price
series are normalized at the actual discontinuity boundary. This matters when
a vendor rewrites only part of the pre-split history (0052 is a real example).
"""
from __future__ import annotations
from functools import lru_cache
from html.parser import HTMLParser
import hashlib
import json
import math
from typing import Any
import pandas as pd
import requests

TWSE_DIVIDEND_URL="https://www.twse.com.tw/zh/ETFortune-institute/dividendList"
TWSE_0050_SPLIT_SOURCE="https://www.twse.com.tw/zh/ETFortune/announcement?company=A00005&date=20250617&fund=0050&seq=1&type=all"
TWSE_0052_SPLIT_SOURCE="https://www.twse.com.tw/zh/ETFortune/announcement?company=A00010&date=20251125&fund=0052&seq=1&type=other"
REQUEST_TIMEOUT_SECONDS=15
SPLIT_DISCONTINUITY_LOW=0.55
SPLIT_DISCONTINUITY_HIGH=1.8
MAX_INFERRED_SPLIT_RELATIVE_ERROR=0.05
KNOWN_SPLIT_DEDUP_DAYS=14
_HEADERS={"Accept":"text/html,application/xhtml+xml","User-Agent":"Mozilla/5.0 (compatible; AI-Stock-Platform/1.0; +https://github.com/zy315220-bit/ai-stock-platform)"}
KNOWN_SPLITS={"0050":[{"effective_date":"2025-06-18","ratio":4.0,"source":TWSE_0050_SPLIT_SOURCE}],"0052":[{"effective_date":"2025-11-26","ratio":7.0,"source":TWSE_0052_SPLIT_SOURCE}]}

# Audited snapshot of the official TWSE ETF distribution table. The live page
# remains the preferred source; this snapshot prevents a transient exchange
# outage from silently deleting dividends from Total Return and competition
# rankings. Keep all four competition ETFs complete across the full ten-year
# competition download window through the snapshot date.
OFFICIAL_DIVIDEND_FALLBACK_REVISION = "TWSE-ETF-DIVIDENDS-10Y-2026-08-25"
OFFICIAL_DIVIDEND_FALLBACK = {
    "0050": (
        ("2017-02-08", "2017-03-14", 1.7),
        ("2017-07-31", "2017-08-31", 0.7),
        ("2018-01-29", "2018-03-13", 2.2),
        ("2018-07-23", "2018-08-27", 0.7),
        ("2019-01-22", "2019-03-08", 2.3),
        ("2019-07-19", "2019-08-22", 0.7),
        ("2020-01-31", "2020-03-06", 2.9),
        ("2020-07-21", "2020-08-24", 0.7),
        ("2021-01-22", "2021-03-09", 3.05),
        ("2021-07-21", "2021-08-24", 0.35),
        ("2022-01-21", "2022-03-04", 3.2),
        ("2022-07-18", "2022-08-19", 1.8),
        ("2023-01-30", "2023-03-07", 2.6),
        ("2023-07-18", "2023-08-11", 1.9),
        ("2024-01-17", "2024-02-21", 3.0),
        ("2024-07-16", "2024-08-09", 1.0),
        ("2025-01-17", "2025-02-20", 2.7),
        ("2025-07-21", "2025-08-08", 0.36),
        ("2026-01-22", "2026-02-11", 1.0),
        ("2026-07-21", "2026-08-10", 0.6),
    ),
    "0056": (
        ("2016-10-26", "2016-11-28", 1.3),
        ("2017-10-30", "2017-12-04", 0.95),
        ("2018-10-23", "2018-11-27", 1.45),
        ("2019-10-23", "2019-11-26", 1.8),
        ("2020-10-28", "2020-12-01", 1.6),
        ("2021-10-22", "2021-11-25", 1.8),
        ("2022-10-19", "2022-11-22", 2.1),
        ("2023-07-18", "2023-08-11", 1.0),
        ("2023-10-19", "2023-11-14", 1.2),
        ("2024-01-17", "2024-02-21", 0.7),
        ("2024-04-18", "2024-05-15", 0.79),
        ("2024-07-16", "2024-08-09", 1.07),
        ("2024-10-17", "2024-11-12", 1.07),
        ("2025-01-17", "2025-02-20", 1.07),
        ("2025-04-23", "2025-05-14", 1.07),
        ("2025-07-21", "2025-08-08", 0.866),
        ("2025-10-23", "2025-11-14", 0.866),
        ("2026-01-22", "2026-02-11", 0.866),
        ("2026-04-23", "2026-05-14", 1.0),
        ("2026-07-21", "2026-08-10", 1.35),
    ),
    "00878": (
        ("2020-11-17", "2020-12-18", 0.05),
        ("2021-02-25", "2021-03-31", 0.15),
        ("2021-05-18", "2021-06-21", 0.25),
        ("2021-08-17", "2021-09-17", 0.3),
        ("2021-11-16", "2021-12-17", 0.28),
        ("2022-02-22", "2022-03-28", 0.3),
        ("2022-05-18", "2022-06-21", 0.32),
        ("2022-08-16", "2022-09-19", 0.28),
        ("2022-11-16", "2022-12-19", 0.28),
        ("2023-02-16", "2023-03-22", 0.27),
        ("2023-05-17", "2023-06-12", 0.27),
        ("2023-08-16", "2023-09-11", 0.35),
        ("2023-11-16", "2023-12-12", 0.35),
        ("2024-02-27", "2024-03-25", 0.4),
        ("2024-05-17", "2024-06-13", 0.51),
        ("2024-08-16", "2024-09-11", 0.55),
        ("2024-11-18", "2024-12-12", 0.55),
        ("2025-02-20", "2025-03-18", 0.5),
        ("2025-05-19", "2025-06-13", 0.47),
        ("2025-08-18", "2025-09-11", 0.4),
        ("2025-11-18", "2025-12-12", 0.4),
        ("2026-02-26", "2026-03-23", 0.42),
        ("2026-05-19", "2026-06-12", 0.66),
        ("2026-08-18", "2026-09-11", 1.01),
    ),
    "00919": (
        ("2023-06-16", "2023-07-14", 0.54),
        ("2023-09-18", "2023-10-17", 0.54),
        ("2023-12-18", "2024-01-12", 0.55),
        ("2024-03-18", "2024-04-15", 0.66),
        ("2024-06-24", "2024-07-15", 0.7),
        ("2024-09-23", "2024-10-15", 0.72),
        ("2024-12-20", "2025-01-13", 0.72),
        ("2025-03-18", "2025-04-15", 0.72),
        ("2025-06-17", "2025-07-11", 0.72),
        ("2025-09-16", "2025-10-15", 0.54),
        ("2025-12-16", "2026-01-13", 0.54),
        ("2026-03-17", "2026-04-14", 0.78),
        ("2026-06-16", "2026-07-13", 1.0),
    ),
}
CORPORATE_ACTION_STATIC_VERSION = hashlib.sha256(
    json.dumps(
        {
            "schema": "tw-corporate-actions-v3",
            "splits": KNOWN_SPLITS,
            "dividend_snapshot_revision": OFFICIAL_DIVIDEND_FALLBACK_REVISION,
            "dividends": OFFICIAL_DIVIDEND_FALLBACK,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
).hexdigest()

class _TableParser(HTMLParser):
 def __init__(self):super().__init__();self.rows=[];self._row=None;self._cell=None
 def handle_starttag(self,tag,attrs):
  if tag=="tr":self._row=[]
  elif tag=="td" and self._row is not None:self._cell=[]
 def handle_data(self,data):
  if self._cell is not None:self._cell.append(data)
 def handle_endtag(self,tag):
  if tag=="td" and self._row is not None and self._cell is not None:self._row.append(" ".join(self._cell).strip());self._cell=None
  elif tag=="tr" and self._row is not None:
   if self._row:self.rows.append(self._row)
   self._row=None;self._cell=None

def _roc_text_date(value):
 parts=value.strip().replace("年","-").replace("月","-").replace("日","").split("-")
 if len(parts)!=3:return None
 try:y,m,d=(int(x) for x in parts);return pd.Timestamp(year=y+1911,month=m,day=d)
 except (TypeError,ValueError):return None

def parse_twse_dividend_html(html,stock_code):
 parser=_TableParser();parser.feed(html);events=[]
 for row in parser.rows:
  if len(row)<6 or row[0].strip()!=stock_code:continue
  ex=_roc_text_date(row[2]);pay=_roc_text_date(row[4])
  try:amount=float(row[5].replace(",","").strip())
  except ValueError:continue
  if ex is None or amount<=0 or not math.isfinite(amount):continue
  events.append({"ex_date":ex.strftime("%Y-%m-%d"),"payment_date":pay.strftime("%Y-%m-%d") if pay is not None else None,"amount":amount,"source":TWSE_DIVIDEND_URL})
 return sorted(events,key=lambda e:e["ex_date"])

@lru_cache(maxsize=128)
def _download_twse_etf_dividends_cached(stock_code,start_year,end_year):
 r=requests.get(TWSE_DIVIDEND_URL,params={"stkNo":stock_code,"startDate":str(start_year),"endDate":str(end_year)},headers=_HEADERS,timeout=REQUEST_TIMEOUT_SECONDS);r.raise_for_status();return tuple((e["ex_date"],e["payment_date"],float(e["amount"])) for e in parse_twse_dividend_html(r.text,stock_code))

def download_twse_etf_dividends(stock_code,*,start,end):
 s=pd.Timestamp(start).normalize();e=pd.Timestamp(end).normalize()
 try:cached=_download_twse_etf_dividends_cached(stock_code,s.year,e.year)
 except (requests.RequestException,ValueError,TypeError):cached=()
 records=cached or OFFICIAL_DIVIDEND_FALLBACK.get(stock_code,())
 source=(
  TWSE_DIVIDEND_URL
  if cached
  else f"{TWSE_DIVIDEND_URL}#snapshot={OFFICIAL_DIVIDEND_FALLBACK_REVISION}"
 )
 return [{"ex_date":x,"payment_date":p,"amount":a,"source":source} for x,p,a in records if s<=pd.Timestamp(x)<=e]

def _split_candidate(prev_close,current_open):
 if prev_close<=0 or current_open<=0:return None
 observed=prev_close/current_open
 if observed>=SPLIT_DISCONTINUITY_HIGH:ratio=float(round(observed))
 elif observed<=SPLIT_DISCONTINUITY_LOW:
  inverse=1.0/observed;rounded=round(inverse)
  if rounded<=0:return None
  ratio=1.0/float(rounded)
 else:return None
 if ratio==0 or not(0.05<=ratio<=20):return None
 error=abs(observed-ratio)/abs(ratio)
 return ratio,error,observed

def _inferred_splits(frame):
 if frame.empty or len(frame)<2:return []
 ordered=frame.sort_index();events=[]
 for pos in range(1,len(ordered)):
  prev=float(ordered.iloc[pos-1]["Close"]);cur=float(ordered.iloc[pos]["Open"]);candidate=_split_candidate(prev,cur)
  if candidate is None:continue
  ratio,error,_=candidate
  if error>MAX_INFERRED_SPLIT_RELATIVE_ERROR:continue
  events.append({"effective_date":pd.Timestamp(ordered.index[pos]).strftime("%Y-%m-%d"),"ratio":ratio,"source":"detected_from_ohlcv_discontinuity"})
 return events

def _same_split_event(a,b):
 try:
  ratio_a=float(a["ratio"]);ratio_b=float(b["ratio"])
  if not math.isclose(ratio_a,ratio_b,rel_tol=MAX_INFERRED_SPLIT_RELATIVE_ERROR,abs_tol=1e-9):return False
  return abs((pd.Timestamp(a["effective_date"])-pd.Timestamp(b["effective_date"])).days)<=KNOWN_SPLIT_DEDUP_DAYS
 except (KeyError,TypeError,ValueError):return False

def validate_corporate_action_basis(frame,stock_code):
 if frame is None or frame.empty or len(frame)<2:return []
 ordered=frame.sort_index();known=KNOWN_SPLITS.get(stock_code,[]);ambiguous=[]
 for pos in range(1,len(ordered)):
  prev=float(ordered.iloc[pos-1]["Close"]);cur=float(ordered.iloc[pos]["Open"])
  if prev<=0 or cur<=0:continue
  observed=prev/cur
  if SPLIT_DISCONTINUITY_LOW<observed<SPLIT_DISCONTINUITY_HIGH:continue
  event_date=pd.Timestamp(ordered.index[pos]).strftime("%Y-%m-%d");candidate=_split_candidate(prev,cur);inferred={"effective_date":event_date,"ratio":candidate[0] if candidate else observed}
  if any(_same_split_event(inferred,k) for k in known):continue
  if candidate is None or candidate[1]>MAX_INFERRED_SPLIT_RELATIVE_ERROR:ambiguous.append({"date":event_date,"observed_ratio":round(observed,6)})
 if ambiguous:
  sample=ambiguous[0];raise ValueError(f"{stock_code} 歷史價格在 {sample['date']} 出現未確認的 corporate-action 跳變（約 {sample['observed_ratio']} 倍）；為避免拆分錯誤污染模擬，本次回測已停止。")
 return ambiguous

def split_events(frame,stock_code):
 """Return official events plus the provider boundary used for normalization.

 The exchange effective date is retained for audit. If the actual OHLCV series
 changes units on a nearby date, adjustment_date records that boundary instead
 of pretending the provider's mixed history is already normalized.
 """
 known=[dict(e) for e in KNOWN_SPLITS.get(stock_code,[])];provider=[dict(e) for e in frame.attrs.get("provider_splits",[]) or []];inferred=_inferred_splits(frame);events=[]
 for official in known:
  item=dict(official);matches=[e for e in inferred if _same_split_event(e,official)]
  if matches:item["adjustment_date"]=min(matches,key=lambda e:abs((pd.Timestamp(e["effective_date"])-pd.Timestamp(official["effective_date"])).days))["effective_date"]
  else:item["adjustment_date"]=item["effective_date"]
  events.append(item)
 for declared in provider:
  if any(_same_split_event(declared,event) for event in events):continue
  item=dict(declared);item["adjustment_date"]=item.get("adjustment_date",item["effective_date"]);events.append(item)
 for event in inferred:
  if any(_same_split_event(event,k) for k in known):continue
  item=dict(event);item["adjustment_date"]=item["effective_date"]
  if not any(_same_split_event(item,e) for e in events):events.append(item)
 return sorted(events,key=lambda e:e["effective_date"])

def adjust_dividends_for_splits(dividends,splits):
 out=[]
 for event in dividends:
  amount=float(event["amount"]);ex=pd.Timestamp(event["ex_date"])
  for split in splits:
   if ex<pd.Timestamp(split["effective_date"]):amount/=float(split["ratio"])
  item=dict(event);item["amount"]=amount;out.append(item)
 return out

def apply_split_adjustments(frame,stock_code):
 if frame is None or frame.empty:return frame
 if frame.attrs.get("split_adjusted") is True:return frame.copy()
 validate_corporate_action_basis(frame,stock_code);adjusted=frame.copy();events=split_events(adjusted,stock_code)
 for event in reversed(events):
  boundary=pd.Timestamp(event.get("adjustment_date",event["effective_date"]));ratio=float(event["ratio"]);mask=adjusted.index<boundary;adjusted.loc[mask,["Open","High","Low","Close"]]/=ratio
  if "Volume" in adjusted.columns:adjusted.loc[mask,"Volume"]*=ratio
 adjusted.attrs.update(frame.attrs);adjusted.attrs["split_adjustments"]=events;adjusted.attrs["price_basis"]="latest-unit split-adjusted";adjusted.attrs["split_adjusted"]=True;adjusted.attrs["corporate_action_validated"]=True;adjusted.attrs["corporate_action_catalog_revision"]=CORPORATE_ACTION_STATIC_VERSION;return adjusted

def attach_official_dividends(frame,stock_code):
 if frame is None or frame.empty:return frame
 output=frame.copy();provider=[dict(event) for event in frame.attrs.get("provider_dividends",[]) or []];is_etf=stock_code.startswith("00");official=download_twse_etf_dividends(stock_code,start=pd.Timestamp(output.index.min()),end=pd.Timestamp(output.index.max())) if is_etf else [];dividends=official or provider;splits=list(output.attrs.get("split_adjustments",[]));output.attrs.update(frame.attrs);output.attrs["dividends"]=adjust_dividends_for_splits(dividends,splits);output.attrs["dividend_source"]=(dividends[0]["source"] if dividends else "unavailable");output.attrs["dividend_provenance"]=("official_twse_etf" if official else "yahoo_provider_events" if provider else "unavailable");output.attrs["corporate_action_catalog_revision"]=CORPORATE_ACTION_STATIC_VERSION;return output

def dividends_by_ex_date(frame):
 totals={}
 for event in frame.attrs.get("dividends",[]):
  ex=str(event.get("ex_date",""));amount=float(event.get("amount",0.0))
  if ex and amount>0:totals[ex]=totals.get(ex,0.0)+amount
 return totals


def clear_corporate_action_cache():
 _download_twse_etf_dividends_cached.cache_clear()
