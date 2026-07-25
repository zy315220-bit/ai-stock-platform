from __future__ import annotations

from numbers import Real
from typing import Any

import pandas as pd


def _get_score(
    result: dict[str, Any],
) -> float:
    """
    從 Score Engine 的字典結果取得總分。
    """

    value = result.get(
        "total_score",
        result.get(
            "score",
            result.get(
                "final_score",
            ),
        ),
    )

    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise RuntimeError(
            "Score Engine 回傳的分數不是有效數字。"
            f"分數內容：{value!r}"
        ) from error


def _extract_score(
    result: Any,
) -> float:
    """
    支援 Score Engine 回傳：

    1. dict
    2. tuple
    3. dataclass 或一般 object
    4. int 或 float

    若是 tuple，會繼續從第一個元素取得分數。
    """

    if isinstance(result, dict):
        return _get_score(result)

    if isinstance(result, tuple):
        if not result:
            raise RuntimeError(
                "Score Engine 回傳了空的 tuple。"
            )

        return _extract_score(
            result[0]
        )

    if isinstance(result, Real):
        return float(result)

    if hasattr(result, "total_score"):
        value = getattr(
            result,
            "total_score",
        )

        try:
            return float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "Score Engine 物件中的 total_score "
                "不是有效數字。"
                f"分數內容：{value!r}"
            ) from error

    if hasattr(result, "score"):
        value = getattr(
            result,
            "score",
        )

        try:
            return float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "Score Engine 物件中的 score "
                "不是有效數字。"
                f"分數內容：{value!r}"
            ) from error

    if hasattr(result, "final_score"):
        value = getattr(
            result,
            "final_score",
        )

        try:
            return float(value)
        except (TypeError, ValueError) as error:
            raise RuntimeError(
                "Score Engine 物件中的 final_score "
                "不是有效數字。"
                f"分數內容：{value!r}"
            ) from error

    raise RuntimeError(
        "無法從 Score Engine 結果取得分數。"
        f"回傳型別：{type(result).__name__}；"
        f"回傳內容：{result!r}"
    )


def _prepare_stock_data(
    df: pd.DataFrame,
    start_date: str,
    end_date: str | None,
) -> pd.DataFrame:
    """
    整理並篩選股票歷史資料。
    """

    if df is None or df.empty:
        raise ValueError(
            "下載到的股票歷史資料為空。"
        )

    df = df.copy()

    # ==============================================
    # 處理 MultiIndex 欄位
    # ==============================================

    if isinstance(
        df.columns,
        pd.MultiIndex,
    ):
        df.columns = [
            str(column[0])
            for column in df.columns
        ]

    df.columns = [
        str(column).strip()
        for column in df.columns
    ]

    if df.columns.duplicated().any():
        duplicated_columns = sorted(
            set(
                df.columns[
                    df.columns.duplicated()
                ].tolist()
            )
        )

        raise ValueError(
            "股票資料包含重複欄位，"
            "請確認一次只下載一個股票代號。"
            f"重複欄位：{duplicated_columns}"
        )

    # ==============================================
    # 統一欄位名稱
    # ==============================================

    column_mapping: dict[str, str] = {}

    for column in df.columns:
        lower_name = column.lower()

        if lower_name == "open":
            column_mapping[column] = "Open"

        elif lower_name == "high":
            column_mapping[column] = "High"

        elif lower_name == "low":
            column_mapping[column] = "Low"

        elif lower_name == "close":
            column_mapping[column] = "Close"

        elif lower_name in {
            "adj close",
            "adj_close",
            "adjclose",
        }:
            column_mapping[column] = "Adj Close"

        elif lower_name == "volume":
            column_mapping[column] = "Volume"

        elif lower_name in {
            "date",
            "datetime",
            "timestamp",
            "time",
        }:
            column_mapping[column] = "Date"

    df = df.rename(
        columns=column_mapping
    )

    required_columns = {
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    }

    missing_columns = (
        required_columns
        - set(df.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            f"股票資料缺少必要欄位："
            f"{missing_text}。"
            f"目前欄位：{list(df.columns)}"
        )

    # ==============================================
    # 處理日期欄位
    # ==============================================

    if "Date" in df.columns:
        df["Date"] = pd.to_datetime(
            df["Date"],
            errors="coerce",
        )

        df = df.dropna(
            subset=["Date"]
        )

        df = df.sort_values(
            "Date"
        )

    else:
        try:
            converted_index = pd.to_datetime(
                df.index,
                errors="coerce",
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                "股票歷史資料沒有可辨識的日期欄位。"
            ) from error

        df.index = converted_index

        df = df.loc[
            ~df.index.isna()
        ]

        df = df.sort_index()

        df.index.name = "Date"

        df = df.reset_index()

    if df.empty:
        raise ValueError(
            "股票歷史資料沒有有效日期。"
        )

    # ==============================================
    # 驗證查詢日期
    # ==============================================

    try:
        start_timestamp = pd.Timestamp(
            start_date
        )

    except (
        TypeError,
        ValueError,
    ) as error:
        raise ValueError(
            f"開始日期格式錯誤："
            f"{start_date}，"
            "請提供有效日期，例如 YYYY-MM-DD。"
        ) from error

    if pd.isna(start_timestamp):
        raise ValueError(
            f"開始日期格式錯誤："
            f"{start_date}，"
            "請提供有效日期，例如 YYYY-MM-DD。"
        )

    if end_date:
        try:
            end_timestamp = pd.Timestamp(
                end_date
            )

        except (
            TypeError,
            ValueError,
        ) as error:
            raise ValueError(
                f"結束日期格式錯誤："
                f"{end_date}，"
                "請提供有效日期，例如 YYYY-MM-DD。"
            ) from error

        if pd.isna(end_timestamp):
            raise ValueError(
                f"結束日期格式錯誤："
                f"{end_date}，"
                "請提供有效日期，例如 YYYY-MM-DD。"
            )

    else:
        end_timestamp = (
            pd.Timestamp
            .today()
            .normalize()
        )

    start_timestamp = (
        start_timestamp.normalize()
    )

    end_timestamp = (
        end_timestamp.normalize()
    )

    if start_timestamp > end_timestamp:
        raise ValueError(
            "開始日期不能晚於結束日期。"
        )

    # ==============================================
    # 篩選日期範圍
    # ==============================================

    df = df.loc[
        (
            df["Date"]
            >= start_timestamp
        )
        & (
            df["Date"]
            <= end_timestamp
        )
    ].copy()

    if df.empty:
        raise ValueError(
            "指定日期範圍內沒有歷史資料："
            f"{start_date} 至 "
            f"{end_date or '今天'}"
        )

    # ==============================================
    # 數值欄位轉換
    # ==============================================

    numeric_columns = [
        "Open",
        "High",
        "Low",
        "Close",
        "Volume",
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce",
        )

    df = df.dropna(
        subset=[
            "Date",
            "Open",
            "High",
            "Low",
            "Close",
            "Volume",
        ]
    )

    # ==============================================
    # 過濾不合理行情資料
    # ==============================================

    df = df.loc[
        (df["Open"] > 0)
        & (df["High"] > 0)
        & (df["Low"] > 0)
        & (df["Close"] > 0)
        & (df["Volume"] >= 0)
        & (df["High"] >= df["Low"])
        & (
            df["High"]
            >= df[["Open", "Close"]].max(
                axis=1
            )
        )
        & (
            df["Low"]
            <= df[["Open", "Close"]].min(
                axis=1
            )
        )
    ].copy()

    if df.empty:
        raise ValueError(
            "清理無效價格資料後，"
            "沒有可用的歷史資料。"
        )

    # ==============================================
    # 移除重複日期
    # ==============================================

    df = df.drop_duplicates(
        subset=["Date"],
        keep="last",
    )

    df = df.sort_values(
        "Date"
    )

    return df.reset_index(
        drop=True
    )


def _get_row_date(
    row: pd.Series,
) -> str:
    """
    將資料列日期轉成 YYYY-MM-DD。
    """

    value = row.get(
        "Date"
    )

    if value is None or pd.isna(value):
        return ""

    try:
        timestamp = pd.Timestamp(
            value
        )

    except (
        TypeError,
        ValueError,
    ):
        return ""

    if pd.isna(timestamp):
        return ""

    return timestamp.strftime(
        "%Y-%m-%d"
    )