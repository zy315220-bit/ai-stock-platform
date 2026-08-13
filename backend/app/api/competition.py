from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, status

from app.services.competition_service import (
    competition_methodology,
    freeze_robot_spec,
    rank_robot_results,
)


router = APIRouter()


@router.get(
    "/methodology",
    summary="取得機器人競賽方法",
)
def get_competition_methodology() -> dict[str, Any]:
    return competition_methodology()


@router.post(
    "/freeze-spec",
    summary="固定並建立機器人規則指紋",
)
def post_freeze_robot_spec(spec: dict[str, Any]) -> dict[str, Any]:
    try:
        return freeze_robot_spec(spec)
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error


@router.post(
    "/rank",
    summary="在公平條件下排名機器人",
)
def post_rank_robot_results(payload: dict[str, Any]) -> dict[str, Any]:
    rows = payload.get("robots")
    confidence = payload.get("confidence", 0.95)

    if not isinstance(rows, list):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="robots 必須是陣列。",
        )

    try:
        return rank_robot_results(
            rows,
            confidence=float(confidence),
        )
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error
