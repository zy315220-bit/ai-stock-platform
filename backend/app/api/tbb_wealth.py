from __future__ import annotations

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()


class SuitabilityRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    loss_tolerance: int = Field(ge=1, le=4)
    investment_horizon: int = Field(ge=1, le=4)
    liquidity_need: int = Field(ge=1, le=4)
    investment_experience: int = Field(ge=1, le=4)


class SuitabilityDecision(BaseModel):
    risk_code: Literal["R1", "R2", "R3", "R4"]
    risk_name: str
    risk_score: int
    max_research_drawdown_percent: float
    per_trade_risk_budget_percent: float
    human_review_required: bool
    blocked_capabilities: list[str]
    allowed_research: list[str]
    governance: dict[str, object]


def _decision(score: int) -> tuple[str, str, float, float]:
    if score <= 6:
        return "R1", "守護型", 8.0, 0.5
    if score <= 9:
        return "R2", "穩健型", 15.0, 1.0
    if score <= 12:
        return "R3", "成長型", 25.0, 1.5
    return "R4", "積極型", 35.0, 2.0


@router.post(
    "/suitability",
    response_model=SuitabilityDecision,
    summary="競賽原型：理財適合度與研究權限決策",
)
def suitability(payload: SuitabilityRequest) -> SuitabilityDecision:
    score = (
        payload.loss_tolerance
        + payload.investment_horizon
        + (5 - payload.liquidity_need)
        + payload.investment_experience
    )
    risk_code, risk_name, max_drawdown, risk_budget = _decision(score)

    return SuitabilityDecision(
        risk_code=risk_code,
        risk_name=risk_name,
        risk_score=score,
        max_research_drawdown_percent=max_drawdown,
        per_trade_risk_budget_percent=risk_budget,
        human_review_required=True,
        blocked_capabilities=[
            "自動下單",
            "付款或資金移轉",
            "繞過 Final Holdout",
            "未通過研究 Gate 的對客推薦",
        ],
        allowed_research=[
            "市場與標的研究",
            "可解釋風險摘要",
            "通過 Gate 的候選研究",
            "提供理專人工覆核的證據包",
        ],
        governance={
            "pii_collected": False,
            "extra_fields_rejected": True,
            "execution_authority": False,
            "final_holdout_interactive_access": False,
            "fail_closed": True,
            "note": (
                "此端點僅產生研究適合度與權限邊界；"
                "不提供個別金融商品適合度認定，也不執行交易。"
            ),
        },
    )
