"""Taiwan stock historical data downloader."""
from typing import Any, Optional
import pandas as pd
import yfinance as yf
from official_data import download_official_history
from corporate_actions import apply_split_adjustments, attach_official_dividends

REQUIRED_OHLCV_COLUMNS=["Open","High","Low","Close","Volume"]

def normalize_stock_code(stock_code:Any)->str:
    if stock_code is None:raise ValueError("股票代號不能是 None。")
    code=str(stock_code).strip().upper()
    if code.endswith(".TWO"):code=code[:-4]
    elif code.endswith(".TW"):code=code[:-3]
    if not code.strip():raise ValueError("股票代號不能空白。")
    return code.strip()

def build_ticker_list(stock_code:Any)->list[str]:
    original=str(stock_code).strip().upper()
    if not original:raise ValueError("股票代號不能空白。")
    code=normalize_stock_code(original)
    if original.endswith(".TWO"):return [f"{code}.TWO"]
    if original.endswith(".TW"):return [f"{code}.TW"]
    return [f"{code}.TW",f"{code}.TWO"]

def flatten_columns(df):
    if df is None:return pd.DataFrame()
    attrs=dict(df.attrs);df=df.copy()
    if isinstance(df.columns,pd.MultiIndex):df.columns=df.columns.get_level_values(0)
    df.columns=[str(c).strip() for c in df.columns];df=df.loc[:,~df.columns.duplicated()].copy();df.attrs.update(attrs);return df

def _normalize_datetime_index(df,timezone="Asia/Taipei",remove_timezone=False):
    if df is None or df.empty:return df
    attrs=dict(df.attrs);df=df.copy()
    try:idx=pd.to_datetime(df.index,errors="coerce")
    except Exception:return df
    valid=~idx.isna();df=df.loc[valid].copy();idx=idx[valid]
    if idx.tz is not None:
        idx=idx.tz_convert(timezone)
        if remove_timezone:idx=idx.tz_localize(None)
    df.index=idx;df=df[~df.index.duplicated(keep="last")].copy().sort_index();df.attrs.update(attrs);return df

def _clean_ohlcv(df,require_all_columns=True):
    if df is None or df.empty:return pd.DataFrame()
    attrs=dict(df.attrs);df=flatten_columns(df);missing=[c for c in REQUIRED_OHLCV_COLUMNS if c not in df.columns]
    if require_all_columns and missing:return pd.DataFrame()
    cols=[c for c in REQUIRED_OHLCV_COLUMNS if c in df.columns]
    if "Close" not in cols:return pd.DataFrame()
    df=df[cols].copy()
    for c in cols:df[c]=pd.to_numeric(df[c],errors="coerce")
    df=df.dropna(subset=["Close"]);df=df[df["Close"]>0]
    if "Volume" in df.columns:df["Volume"]=df["Volume"].fillna(0).clip(lower=0)
    df=df[~df.index.duplicated(keep="last")].copy().sort_index();df.attrs.update(attrs);return df

def _download_yfinance(ticker,period,interval,prepost=False):
    try:df=yf.download(tickers=ticker,period=period,interval=interval,progress=False,auto_adjust=False,threads=False,prepost=prepost,group_by="column")
    except Exception:return pd.DataFrame()
    if df is None:return pd.DataFrame()
    # Yahoo's historical OHLC series is split-normalized even with auto_adjust=False;
    # auto_adjust controls dividend/Adj Close behavior, not reintroducing pre-split units.
    df.attrs["source"]="Yahoo Finance";df.attrs["split_adjusted"]=True;df.attrs["price_basis"]="yahoo_split_adjusted_close";return df

def _aggregate_latest_intraday(intraday):
    if intraday is None or intraday.empty:return None
    intraday=_normalize_datetime_index(intraday,remove_timezone=False)
    if intraday.empty:return None
    latest=intraday.index[-1];rows=intraday.loc[intraday.index.date==latest.date()].copy()
    if rows.empty:return None
    o=rows["Open"].dropna();c=rows["Close"].dropna()
    if o.empty or c.empty:return None
    return {"date":pd.Timestamp(latest.date()),"Open":float(o.iloc[0]),"High":float(rows["High"].max()),"Low":float(rows["Low"].min()),"Close":float(c.iloc[-1]),"Volume":float(rows["Volume"].fillna(0).sum())}

def _merge_latest_intraday(daily,intraday):
    summary=_aggregate_latest_intraday(intraday)
    if summary is None:return daily
    attrs=dict(daily.attrs);daily=_normalize_datetime_index(daily,remove_timezone=True).copy()
    for c in REQUIRED_OHLCV_COLUMNS:daily.loc[summary["date"],c]=summary[c]
    daily=daily[~daily.index.duplicated(keep="last")].copy().sort_index();daily.attrs.update(attrs);return daily

def _set_dataframe_attributes(df,ticker,interval,source="Yahoo Finance"):
    df.attrs.update({"ticker":ticker,"stock_code":normalize_stock_code(ticker),"market":"上櫃" if ticker.endswith(".TWO") else "上市","interval":interval,"source":source});return df

def _normalize_price_basis(daily,stock_code,source):
    daily=daily.copy();daily.attrs["source"]=source
    if source=="Yahoo Finance":
        daily.attrs["split_adjusted"]=True;daily.attrs.setdefault("price_basis","yahoo_split_adjusted_close");return daily
    return apply_split_adjustments(daily,stock_code)

def download_stock(stock_code:Any,daily_period="max",update_with_intraday=True,intraday_period="5d",intraday_interval="5m",prefer_official=False,official_months=10,force_official_refresh=False,include_corporate_actions=False):
    errors=[]
    for ticker in build_ticker_list(stock_code):
        market="上櫃" if ticker.endswith(".TWO") else "上市";code=normalize_stock_code(ticker);official_daily=pd.DataFrame()
        if prefer_official:
            official_daily=download_official_history(code,market=market,months=official_months,force_refresh=force_official_refresh);daily=_clean_ohlcv(official_daily);daily_source=str(official_daily.attrs.get("source","官方交易所資料"))
        else:
            daily=_clean_ohlcv(_download_yfinance(ticker,daily_period,"1d",False));daily_source="Yahoo Finance"
        if daily.empty:
            if prefer_official:
                daily=_clean_ohlcv(_download_yfinance(ticker,daily_period,"1d",False));daily_source="Yahoo Finance"
            else:
                official_daily=download_official_history(code,market=market,months=official_months,force_refresh=force_official_refresh);daily=_clean_ohlcv(official_daily);daily_source=str(official_daily.attrs.get("source","官方交易所資料"))
        if daily.empty:errors.append(f"{ticker}：Yahoo 與官方來源皆沒有有效日線資料");continue
        daily=_normalize_datetime_index(daily,remove_timezone=True);daily=_normalize_price_basis(daily,code,daily_source)
        if include_corporate_actions:daily=attach_official_dividends(daily,code)
        if update_with_intraday and daily_source=="Yahoo Finance":
            intraday=_clean_ohlcv(_download_yfinance(ticker,intraday_period,intraday_interval,False))
            if not intraday.empty:daily=_merge_latest_intraday(daily,intraday)
        daily=daily.dropna(subset=["Open","High","Low","Close"]).copy()
        if daily.empty:errors.append(f"{ticker}：清理後沒有可用資料");continue
        return _set_dataframe_attributes(daily,ticker,"1d",daily_source)
    detail="；".join(errors);raise ValueError(f"找不到股票代號 {normalize_stock_code(stock_code)}，請確認股票代號是否正確。"+(f" 詳細資訊：{detail}。" if detail else ""))

def download_hourly_stock(stock_code:Any,period="60d",interval="60m"):
    errors=[]
    for ticker in build_ticker_list(stock_code):
        hourly=_clean_ohlcv(_download_yfinance(ticker,period,interval,False))
        if hourly.empty:errors.append(f"{ticker}：沒有有效60分鐘資料");continue
        hourly=_normalize_datetime_index(hourly,remove_timezone=False).dropna(subset=["Open","High","Low","Close"]).copy()
        if not hourly.empty:return _set_dataframe_attributes(hourly,ticker,interval)
    raise ValueError(f"無法取得 {normalize_stock_code(stock_code)} 的60分鐘資料。"+(f" 詳細資訊：{'；'.join(errors)}。" if errors else ""))
