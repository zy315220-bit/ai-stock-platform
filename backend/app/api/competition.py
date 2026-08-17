from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from starlette.concurrency import run_in_threadpool

from app.services.competition_service import competition_methodology, freeze_robot_spec, rank_robot_results
from app.services.competition_reliable import DEFAULT_INITIAL_CAPITAL, MAX_INITIAL_CAPITAL, run_competition
from app.services import competition_runner as legacy
from app.services.cscv_analysis import analyze_historical_selection_overfit

router = APIRouter()


@router.get("/run", summary="執行固定規則機器人的公平競賽", description="使用相同股票池、初始資金、交易成本與 ATR 風控，執行 2 個月歷史檢查及 1 個月 walk-forward 模擬；正式排序只使用 forward 區間，區間末未平倉部位採 mark-to-market。")
async def get_competition_run(initial_capital: float = Query(default=DEFAULT_INITIAL_CAPITAL, gt=0, le=MAX_INITIAL_CAPITAL, description="每個機器人的相同初始資金。")) -> dict[str, Any]:
    try:
        return await run_in_threadpool(run_competition, initial_capital)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except TimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="取得官方歷史資料逾時，請稍後再執行競賽。") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="機器人競賽目前無法完成，請稍後再試。") from error


@router.get(
    "/pbo",
    summary="執行跨時間 CSCV/PBO 過度擬合診斷",
    description="使用共同官方歷史資料，把固定策略切成不重疊時間區間，建立策略績效矩陣並執行 CSCV/PBO。此結果是選拔偏誤診斷，不是未來虧損機率。",
)
async def get_competition_pbo(
    initial_capital: float = Query(default=DEFAULT_INITIAL_CAPITAL, gt=0, le=MAX_INITIAL_CAPITAL),
    slice_months: int = Query(default=1, ge=1, le=3),
    max_slices: int = Query(default=12, ge=4, le=12),
) -> dict[str, Any]:
    if max_slices % 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSCV/PBO 的 max_slices 必須是偶數。")
    try:
        frames, sources = await run_in_threadpool(legacy._download_competition_frames)
        result = await run_in_threadpool(
            analyze_historical_selection_overfit,
            frames,
            initial_capital=initial_capital,
            slice_months=slice_months,
            max_slices=max_slices,
        )
        result["data_sources"] = sources
        return result
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except TimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="取得 CSCV/PBO 所需官方歷史資料逾時，請稍後再試。") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CSCV/PBO 分析目前無法完成，請稍後再試。") from error


@router.get("/methodology", summary="取得機器人競賽方法")
def get_competition_methodology() -> dict[str, Any]:
    return competition_methodology()


@router.post("/freeze-spec", summary="固定並建立機器人規則指紋")
def post_freeze_robot_spec(spec: dict[str, Any]) -> dict[str, Any]:
    try:
        return freeze_robot_spec(spec)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error


@router.post("/rank", summary="在公平條件下排名機器人")
def post_rank_robot_results(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("robots")
    confidence = payload.get("confidence", 0.95)
    if not isinstance(rows, list):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="robots 必須是陣列。")
    try:
        return rank_robot_results(rows, confidence=float(confidence))
    except (TypeError, ValueError) as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
