from __future__ import annotations

import logging
from datetime import date
from typing import Any

from fastapi import (
    APIRouter,
    HTTPException,
    Path,
    Query,
    status,
)
from starlette.concurrency import run_in_threadpool

from app.services.analysis_service import analyze_stock
from app.services.backtest_service import backtest_stock


logger = logging.getLogger(__name__)

router = APIRouter()


def _normalize_stock_code(
    stock_code: str,
) -> str:
    """
    整理 API 路徑中的股票代號。
    """

    normalized_code = stock_code.strip().upper()

    if not normalized_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="股票代號不能空白。",
        )

    return normalized_code


def _validate_service_result(
    result: Any,
    *,
    stock_code: str,
    service_name: str,
) -> dict[str, Any]:
    """
    確保 service 層回傳可供 FastAPI 序列化的字典。
    """

    if isinstance(result, dict):
        return result

    logger.error(
        "股票 %s 的%s結果格式錯誤：%s",
        stock_code,
        service_name,
        type(result).__name__,
    )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"{service_name}服務回傳了無效資料。",
    )


def _raise_service_http_error(
    error: Exception,
    *,
    stock_code: str,
    service_name: str,
) -> None:
    """
    將 service 層例外轉換成一致的 HTTP 錯誤。
    """

    if isinstance(error, HTTPException):
        raise error

    if isinstance(error, ValueError):
        logger.warning(
            "股票%s輸入或資料錯誤：code=%s, error=%s",
            service_name,
            stock_code,
            error,
        )

        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    if isinstance(error, TimeoutError):
        logger.error(
            "股票%s逾時：code=%s",
            service_name,
            stock_code,
            exc_info=True,
        )

        timeout_message = (
            "取得股票資料逾時，請稍後再試。"
            if service_name == "分析"
            else "取得歷史股票資料逾時，請稍後再試。"
        )

        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=timeout_message,
        ) from error

    if isinstance(error, RuntimeError):
        logger.error(
            "股票%s服務錯誤：code=%s, error=%s",
            service_name,
            stock_code,
            error,
            exc_info=True,
        )

        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error

    logger.error(
        "股票%s發生未預期錯誤：code=%s",
        service_name,
        stock_code,
        exc_info=True,
    )

    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail=f"股票{service_name}失敗，請稍後再試。",
    ) from error


@router.get(
    "/{stock_code}/analysis",
    summary="分析指定股票",
    description=(
        "取得股票行情、技術指標、AI 評分、交易計畫與圖表資料。"
    ),
    response_description="股票完整分析結果",
)
async def get_stock_analysis(
    stock_code: str = Path(
        ...,
        min_length=1,
        max_length=20,
        description=(
            "台股股票代號，例如 "
            "2330、0056、6488.TWO"
        ),
        examples=["2330"],
    ),
) -> dict[str, Any]:
    """
    執行股票分析。

    真實資料模式會依序：

    1. 下載日線與 60 分鐘資料
    2. 計算技術指標
    3. 呼叫 Score Engine V2
    4. 回傳前端需要的分析結果
    """

    normalized_code = _normalize_stock_code(
        stock_code
    )

    try:
        result = await run_in_threadpool(
            analyze_stock,
            normalized_code,
        )

    except Exception as error:
        _raise_service_http_error(
            error,
            stock_code=normalized_code,
            service_name="分析",
        )

    return _validate_service_result(
        result,
        stock_code=normalized_code,
        service_name="分析",
    )


@router.get(
    "/{stock_code}/backtest",
    summary="回測指定股票",
    description=(
        "使用歷史資料回測 Score Engine。"
        "當分數達到進場門檻時，於下一個交易日開盤買進；"
        "當分數低於出場門檻時，於下一個交易日開盤賣出。"
    ),
    response_description="股票回測結果",
)
async def get_stock_backtest(
    stock_code: str = Path(
        ...,
        min_length=1,
        max_length=20,
        description=(
            "台股股票代號，例如 "
            "2330、0056、6488.TWO"
        ),
        examples=["0056"],
    ),
    start_date: date = Query(
        default=date(2023, 1, 1),
        description="回測開始日期，格式為 YYYY-MM-DD",
    ),
    end_date: date | None = Query(
        default=None,
        description="回測結束日期，格式為 YYYY-MM-DD",
    ),
    entry_score: float = Query(
        default=75,
        ge=0,
        le=100,
        description="進場分數門檻",
    ),
    exit_score: float = Query(
        default=55,
        ge=0,
        le=100,
        description="出場分數門檻",
    ),
    initial_capital: float = Query(
        default=100_000,
        gt=0,
        description="初始資金",
    ),
) -> dict[str, Any]:
    """
    執行股票歷史回測。

    回測規則：

    1. 當日收盤後計算分數
    2. 分數達到進場門檻，下一交易日開盤買進
    3. 分數低於出場門檻，下一交易日開盤賣出
    4. 回傳總報酬、勝率、最大回撤與交易紀錄
    """

    normalized_code = _normalize_stock_code(
        stock_code
    )

    if entry_score <= exit_score:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="進場分數必須高於出場分數。",
        )

    if (
        end_date is not None
        and end_date < start_date
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="結束日期不能早於開始日期。",
        )

    try:
        result = await run_in_threadpool(
            backtest_stock,
            stock_code=normalized_code,
            start_date=start_date.isoformat(),
            end_date=(
                end_date.isoformat()
                if end_date is not None
                else None
            ),
            entry_score=entry_score,
            exit_score=exit_score,
            initial_capital=initial_capital,
        )

    except Exception as error:
        _raise_service_http_error(
            error,
            stock_code=normalized_code,
            service_name="回測",
        )

    return _validate_service_result(
        result,
        stock_code=normalized_code,
        service_name="回測",
    )