"""Corporate-action support for Taiwan ETF historical simulations.

Split normalization is idempotent. Raw official price series are validated
fail-closed: a split-like discontinuity must closely match a plausible split or
reverse-split ratio, otherwise the research simulation is rejected.
"""
from __future__ import annotations
from functools import lru_cache
from html.parser import HTMLParser
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
# Vendor/official OHLCV can place the same corporate-action discontinuity a few
# trading days away from the exchange effective date. Treat a matching-ratio
# inference near a known event as the same event, never as a second split.
KNOWN_SPLIT_DEDUP_DAYS=14
_HEADERS={"Accept":"text/html,application/xhtml+xml","User-Agent":"Mozilla/5.0 (compatible; AI-Stock-Platform/1.0; +https://github.com/zy315220-bit/ai-stock-platform)"}
KNOWN_SPLITS={"0050":[{"effective_date":"2025-06-18","ratio":4.0,"source":TWSE_0050_SPLIT_SOURCE}],"0052":[{"effective_date":"2025-11-26","ratio":7.0,"source":TWSE_0052_SPLIT_SOURCE}]}
OFFICIAL_DIVIDEND_FALLBACK={"0050":(("2020-01-31","2020-03-06",2.9),("2020-07-21","2020-08-24",0.7),("2021-01-22","2021-03-09",3.05),("2021-07-21","2021-08-24",0.35),("2022-01-21","2022-03-04",3.2),("2022-07-18","2022-08-19",1.8),("2023-01-30","2023-03-07",2.6),("2023-07-18","2023-08-11",1.9),("2024-01-17","2024-02-21",3.0),("2024-07-16","2024-08-09",1.0),("2025-01-17","2025-02-20",2.7),("2025-07-21","2025-08-08",0.36),("2026-01-22","2026-02-11",1.0),("2026-07-21","2026-08-10",0.6)),"0056":(("2020-10-28","2020-12-01",1.6),("2021-10-22","2021-11-25",1.8),("2022-10-19","2022-11-22",2.1)),"00878":(),"00919":()}

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
 return [{"ex_date":x,"payment_date":p,"amount":a,"source":TWSE_DIVIDEND_URL} for x,p,a in records if s<=pd.Timestamp(x)<=e]

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
  events.append({"effective_date":pd.Timestamp(ordered.index[pos]).strftime("%Y-%m-%d"),"ratio":ratio,"source":"detected_from_official_ohlcv_discontinuity"})
 return events

def _same_split_event(a,b):
 try:
  ratio_a=float(a["ratio"]);ratio_b=float(b["ratio"])
  if not math.isclose(ratio_a,ratio_b,rel_tol=MAX_INFERRED_SPLIT_RELATIVE_ERROR,abs_tol=1e-9):return False
  days=abs((pd.Timestamp(a["effective_date"])-pd.Timestamp(b["effective_date"])).days)
  return days<=KNOWN_SPLIT_DEDUP_DAYS
 except (KeyError,TypeError,ValueError):return False

def validate_corporate_action_basis(frame,stock_code):
 if frame is None or frame.empty or len(frame)<2:return []
 ordered=frame.sort_index();known=KNOWN_SPLITS.get(stock_code,[]);ambiguous=[]
 for pos in range(1,len(ordered)):
  prev=float(ordered.iloc[pos-1]["Close"]);cur=float(ordered.iloc[pos]["Open"])
  if prev<=0 or cur<=0:continue
  observed=prev/cur
  if SPLIT_DISCONTINUITY_LOW<observed<SPLIT_DISCONTINUITY_HIGH:continue
  event_date=pd.Timestamp(ordered.index[pos]).strftime("%Y-%m-%d");candidate=_split_candidate(prev,cur)
  inferred={"effective_date":event_date,"ratio":candidate[0] if candidate else observed}
  if any(_same_split_event(inferred,k) for k in known):continue
  if candidate is None or candidate[1]>MAX_INFERRED_SPLIT_RELATIVE_ERROR:ambiguous.append({"date":event_date,"observed_ratio":round(observed,6)})
 if ambiguous:
  sample=ambiguous[0]
  raise ValueError(f"{stock_code} 歷史價格在 {sample['date']} 出現未確認的 corporate-action 跳變（約 {sample['observed_ratio']} 倍）；為避免拆分錯誤污染模擬，本次回測已停止。")
 return ambiguous

def split_events(frame,stock_code):
 known=[dict(e) for e in KNOWN_SPLITS.get(stock_code,[])];inferred=_inferred_splits(frame);events=list(known)
 for event in inferred:
  # Known TWSE metadata is authoritative. Do not apply a nearby matching vendor
  # discontinuity as another corporate action.
  if any(_same_split_event(event,k) for k in known):continue
  if not any(_same_split_event(event,e) for e in events):events.append(event)
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
 validate_corporate_action_basis(frame,stock_code)
 adjusted=frame.copy();events=split_events(adjusted,stock_code)
 for event in reversed(events):
  effective=pd.Timestamp(event["effective_date"]);ratio=float(event["ratio"]);mask=adjusted.index<effective;adjusted.loc[mask,["Open","High","Low","Close"]]/=ratio
  if "Volume" in adjusted.columns:adjusted.loc[mask,"Volume"]*=ratio
 adjusted.attrs.update(frame.attrs);adjusted.attrs["split_adjustments"]=events;adjusted.attrs["price_basis"]="latest-unit split-adjusted";adjusted.attrs["split_adjusted"]=True;adjusted.attrs["corporate_action_validated"]=True;return adjusted

def attach_official_dividends(frame,stock_code):
 if frame is None or frame.empty:return frame
 output=frame.copy();dividends=download_twse_etf_dividends(stock_code,start=pd.Timestamp(output.index.min()),end=pd.Timestamp(output.index.max()));splits=list(output.attrs.get("split_adjustments",[]));output.attrs.update(frame.attrs);output.attrs["dividends"]=adjust_dividends_for_splits(dividends,splits);output.attrs["dividend_source"]=TWSE_DIVIDEND_URL;return output

def dividends_by_ex_date(frame):
 totals={}
 for event in frame.attrs.get("dividends",[]):
  ex=str(event.get("ex_date",""));amount=float(event.get("amount",0.0))
  if ex and amount>0:totals[ex]=totals.get(ex,0.0)+amount
 return totals
