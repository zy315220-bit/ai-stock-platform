from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query, status
from starlette.concurrency import run_in_threadpool

from app.services.competition_service import (
    competition_methodology,
    freeze_robot_spec,
    rank_robot_results,
)
from app.services.competition_runner import (
    DEFAULT_INITIAL_CAPITAL,
    MAX_INITIAL_CAPITAL,
    run_competition,
    _download_competition_frames,
    run_competition_on_frames,
)
from app.services.competition_dataset_guard import (
    competition_dataset_manifest,
    prepare_competition_frame,
)

router = APIRouter()


def _run_fresh_competition(initial_capital: float) -> dict[str, Any]:
    """Run against freshly validated corporate-action datasets, bypassing stale cache."""
    frames, sources, coverage = _download_competition_frames()
    safe_frames = {
        code: prepare_competition_frame(frame, code)
        for code, frame in frames.items()
    }
    manifest = competition_dataset_manifest(safe_frames)
    result = run_competition_on_frames(
        safe_frames,
        initial_capital=initial_capital,
        sources=sources,
        coverage=coverage,
    )
    # Bind the externally visible run identity to the exact normalized datasets.
    old_run_id = str(result.get("run_id", ""))
    result["legacy_run_id"] = old_run_id
    result["dataset_fingerprint"] = manifest["fingerprint"]
    result["dataset_manifest"] = manifest["symbols"]
    result["run_id"] = f"{old_run_id}-{manifest['fingerprint'][:8]}"
    result["cache_policy"] = "fresh-corporate-action-validated"
    return result


@router.get(
    "/run",
    summary="執行 16 個固定規則機器人的公平競賽",
    description=(
        "使用相同股票池、初始資金、交易成本與 ATR 風控，"
        "執行前 4 年歷史檢查及最後 1 年 walk-forward 模擬；"
        "正式排序只使用 forward 區間。每次執行先重新驗證 corporate-action 資料版本，"
        "避免拆分/股利修正後沿用舊排行榜快取。"
    ),
)
async def get_competition_run(
    initial_capital: float = Query(
        default=DEFAULT_INITIAL_CAPITAL,
        gt=0,
        le=MAX_INITIAL_CAPITAL,
        description="每個機器人的相同初始資金。",
    ),
) -> dict[str, Any]:
    try:
        return await run_in_threadpool(_run_fresh_competition, initial_capital)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(error)) from error
    except TimeoutError as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="取得官方歷史資料逾時，請稍後再執行競賽。",
        ) from error
    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="機器人競賽目前無法完成，請稍後再試。",
        ) from error


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
