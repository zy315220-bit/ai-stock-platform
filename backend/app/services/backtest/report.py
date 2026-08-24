from __future__ import annotations

from numbers import Real
from typing import Any

import pandas as pd


def _get_score(result: dict[str, Any]) -> float:
    value=result.get("total_score",result.get("score",result.get("final_score")))
    try:return float(value)
    except (TypeError,ValueError) as error:raise RuntimeError(f"Score Engine 回傳的分數不是有效數字。分數內容：{value!r}") from error


def _extract_score(result: Any) -> float:
    if isinstance(result,dict):return _get_score(result)
    if isinstance(result,tuple):
        if not result:raise RuntimeError("Score Engine 回傳了空的 tuple。")
        return _extract_score(result[0])
    if isinstance(result,Real):return float(result)
    for name in ("total_score","score","final_score"):
        if hasattr(result,name):
            value=getattr(result,name)
            try:return float(value)
            except (TypeError,ValueError) as error:raise RuntimeError(f"Score Engine 物件中的 {name} 不是有效數字。分數內容：{value!r}") from error
    raise RuntimeError(f"無法從 Score Engine 結果取得分數。回傳型別：{type(result).__name__}；回傳內容：{result!r}")


def _prepare_stock_data(df: pd.DataFrame,start_date: str,end_date: str|None)->pd.DataFrame:
    """Prepare backtest data without losing research-integrity metadata."""
    if df is None or df.empty:raise ValueError("下載到的股票歷史資料為空。")
    source_attrs=dict(df.attrs)
    df=df.copy()
    if isinstance(df.columns,pd.MultiIndex):df.columns=[str(column[0]) for column in df.columns]
    df.columns=[str(column).strip() for column in df.columns]
    if df.columns.duplicated().any():
        duplicated_columns=sorted(set(df.columns[df.columns.duplicated()].tolist()))
        raise ValueError(f"股票資料包含重複欄位，請確認一次只下載一個股票代號。重複欄位：{duplicated_columns}")
    mapping={}
    for column in df.columns:
        lower=column.lower()
        if lower=="open":mapping[column]="Open"
        elif lower=="high":mapping[column]="High"
        elif lower=="low":mapping[column]="Low"
        elif lower=="close":mapping[column]="Close"
        elif lower in {"adj close","adj_close","adjclose"}:mapping[column]="Adj Close"
        elif lower=="volume":mapping[column]="Volume"
        elif lower in {"date","datetime","timestamp","time"}:mapping[column]="Date"
    df=df.rename(columns=mapping)
    required={"Open","High","Low","Close","Volume"};missing=required-set(df.columns)
    if missing:raise ValueError(f"股票資料缺少必要欄位：{', '.join(sorted(missing))}。目前欄位：{list(df.columns)}")
    if "Date" in df.columns:
        df["Date"]=pd.to_datetime(df["Date"],errors="coerce");df=df.dropna(subset=["Date"]).sort_values("Date")
    else:
        try:converted=pd.to_datetime(df.index,errors="coerce")
        except (TypeError,ValueError) as error:raise ValueError("股票歷史資料沒有可辨識的日期欄位。") from error
        df.index=converted;df=df.loc[~df.index.isna()].sort_index();df.index.name="Date";df=df.reset_index()
    if df.empty:raise ValueError("股票歷史資料沒有有效日期。")
    try:start=pd.Timestamp(start_date)
    except (TypeError,ValueError) as error:raise ValueError(f"開始日期格式錯誤：{start_date}，請提供有效日期，例如 YYYY-MM-DD。") from error
    if pd.isna(start):raise ValueError(f"開始日期格式錯誤：{start_date}，請提供有效日期，例如 YYYY-MM-DD。")
    if end_date:
        try:end=pd.Timestamp(end_date)
        except (TypeError,ValueError) as error:raise ValueError(f"結束日期格式錯誤：{end_date}，請提供有效日期，例如 YYYY-MM-DD。") from error
        if pd.isna(end):raise ValueError(f"結束日期格式錯誤：{end_date}，請提供有效日期，例如 YYYY-MM-DD。")
    else:end=pd.Timestamp.today().normalize()
    start=start.normalize();end=end.normalize()
    if start>end:raise ValueError("開始日期不能晚於結束日期。")
    df=df.loc[(df["Date"]>=start)&(df["Date"]<=end)].copy()
    if df.empty:raise ValueError(f"指定日期範圍內沒有歷史資料：{start_date} 至 {end_date or '今天'}")
    for column in ["Open","High","Low","Close","Volume"]:df[column]=pd.to_numeric(df[column],errors="coerce")
    df=df.dropna(subset=["Date","Open","High","Low","Close","Volume"])
    df=df.loc[(df["Open"]>0)&(df["High"]>0)&(df["Low"]>0)&(df["Close"]>0)&(df["Volume"]>=0)&(df["High"]>=df["Low"])&(df["High"]>=df[["Open","Close"]].max(axis=1))&(df["Low"]<=df[["Open","Close"]].min(axis=1))].copy()
    if df.empty:raise ValueError("清理無效價格資料後，沒有可用的歷史資料。")
    df=df.drop_duplicates(subset=["Date"],keep="last").sort_values("Date").reset_index(drop=True)
    # pandas transformations can discard attrs depending on operation/version.
    # Restore the authoritative source/basis/corporate-action audit trail so
    # benchmark, diagnostics and downstream research all see the same basis.
    df.attrs.update(source_attrs)
    return df


def _get_row_date(row:pd.Series)->str:
    value=row.get("Date")
    if value is None or pd.isna(value):return ""
    try:return pd.Timestamp(value).strftime("%Y-%m-%d")
    except (TypeError,ValueError):return str(value)
