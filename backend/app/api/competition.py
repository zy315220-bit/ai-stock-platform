from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from starlette.concurrency import run_in_threadpool

from app.services.champion_gate import evaluate_champion_gate
from app.services.competition_service import competition_methodology, freeze_robot_spec, rank_robot_results
from app.services.competition_reliable import DEFAULT_INITIAL_CAPITAL, MAX_INITIAL_CAPITAL, run_competition, run_competition_on_frames
from app.services.cscv_analysis import analyze_historical_selection_overfit
from app.services.research_dataset import load_shared_research_dataset

router = APIRouter()


@router.get("/run", summary="執行固定規則機器人的公平競賽", description="使用共用長期官方資料集、相同股票池、初始資金、交易成本與 ATR 風控；正式排序只使用最後 1 個月 forward 區間。")
async def get_competition_run(initial_capital: float = Query(default=DEFAULT_INITIAL_CAPITAL, gt=0, le=MAX_INITIAL_CAPITAL, description="每個機器人的相同初始資金。")) -> dict[str, Any]:
    try:
        return await run_in_threadpool(run_competition, initial_capital)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except TimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="取得官方歷史資料逾時，請稍後再執行競賽。") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="機器人競賽目前無法完成，請稍後再試。") from error


@router.get("/pbo", summary="執行跨時間 CSCV/PBO 過度擬合診斷", description="使用共用長期官方歷史資料建立策略績效矩陣並執行 CSCV/PBO。")
async def get_competition_pbo(
    initial_capital: float = Query(default=DEFAULT_INITIAL_CAPITAL, gt=0, le=MAX_INITIAL_CAPITAL),
    slice_months: int = Query(default=1, ge=1, le=3),
    max_slices: int = Query(default=12, ge=4, le=60),
) -> dict[str, Any]:
    if max_slices % 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="CSCV/PBO 的 max_slices 必須是偶數。")
    try:
        dataset = await run_in_threadpool(load_shared_research_dataset)
        result = await run_in_threadpool(
            analyze_historical_selection_overfit,
            dataset["frames"],
            initial_capital=initial_capital,
            slice_months=slice_months,
            max_slices=max_slices,
        )
        result["data_sources"] = dataset["sources"]
        result["research_history"] = dataset["universe_coverage"]
        return result
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except TimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="取得 CSCV/PBO 所需官方歷史資料逾時，請稍後再試。") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CSCV/PBO 分析目前無法完成，請稍後再試。") from error


@router.get("/champion", summary="執行正式冠軍資格判定", description="使用同一份共用長期官方資料，同時執行公平競賽與 CSCV/PBO，並只對競賽 leader 本人套用 Champion Gate。")
async def get_official_champion(
    initial_capital: float = Query(default=DEFAULT_INITIAL_CAPITAL, gt=0, le=MAX_INITIAL_CAPITAL),
    slice_months: int = Query(default=1, ge=1, le=3),
    max_slices: int = Query(default=12, ge=4, le=60),
) -> dict[str, Any]:
    if max_slices % 2:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="正式冠軍 CSCV/PBO 的 max_slices 必須是偶數。")
    try:
        dataset = await run_in_threadpool(load_shared_research_dataset)
        competition = await run_in_threadpool(
            run_competition_on_frames,
            dataset["frames"],
            initial_capital=initial_capital,
            sources=dataset["sources"],
        )
        competition["research_history"] = dataset["universe_coverage"]
        pbo_analysis = await run_in_threadpool(
            analyze_historical_selection_overfit,
            dataset["frames"],
            initial_capital=initial_capital,
            slice_months=slice_months,
            max_slices=max_slices,
        )
        champion = evaluate_champion_gate(competition=competition, pbo_analysis=pbo_analysis)
        return {
            "status": "completed",
            "champion": champion,
            "competition_run_id": competition.get("run_id"),
            "competition_leader": competition.get("leader"),
            "pbo_percent": pbo_analysis.get("pbo", {}).get("pbo_percent"),
            "slice_count": pbo_analysis.get("slice_count"),
            "strategy_count": pbo_analysis.get("strategy_count"),
            "data_sources": dataset["sources"],
            "research_history": dataset["universe_coverage"],
            "policy": champion["policy"],
            "warning": "正式冠軍資格是歷史與 forward 統計證據的品質閘門，不代表未來獲利保證。",
        }
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except TimeoutError as error:
        raise HTTPException(status_code=status.HTTP_504_GATEWAY_TIMEOUT, detail="取得正式冠軍判定所需資料逾時，請稍後再試。") from error
    except Exception as error:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="正式冠軍資格判定目前無法完成，請稍後再試。") from error


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
