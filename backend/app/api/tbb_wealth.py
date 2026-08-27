from __future__ import annotations

import hashlib
import json
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter()


GoalPriority = Literal["liquidity", "income", "growth", "legacy"]
DecisionState = Literal["RESEARCH_ALLOWED", "REVIEW_REQUIRED"]
Impact = Literal["supports", "limits", "neutral"]
StressState = Literal["PASS", "REVIEW", "BLOCK"]

MODEL_VERSION = "bizwealth-guard-v2.1"


class SuitabilityRequest(BaseModel):
    """Coarse, non-identifying inputs for the competition prototype.

    The endpoint intentionally rejects exact balances, names, account numbers,
    national IDs and every field outside this fixed schema.
    """

    model_config = ConfigDict(extra="forbid")

    loss_tolerance: int = Field(ge=1, le=4)
    investment_horizon: int = Field(ge=1, le=4)
    liquidity_need: int = Field(ge=1, le=4)
    investment_experience: int = Field(ge=1, le=4)
    income_stability: int = Field(ge=1, le=4)
    business_dependency: int = Field(ge=1, le=4)
    wealth_concentration: int = Field(ge=1, le=4)
    goal_priority: GoalPriority


class FactorExplanation(BaseModel):
    factor: str
    impact: Impact
    explanation: str


class AllocationBucket(BaseModel):
    name: str
    target_percent: int
    range_low_percent: int
    range_high_percent: int
    purpose: str


class StressCheck(BaseModel):
    scenario: str
    state: StressState
    observation: str
    advisor_action: str


class GovernanceDecision(BaseModel):
    pii_collected: bool
    exact_balance_collected: bool
    prototype_persists_profile: bool
    extra_fields_rejected: bool
    execution_authority: bool
    payment_authority: bool
    final_holdout_interactive_access: bool
    human_review_required: bool
    fail_closed: bool


class DecisionAudit(BaseModel):
    model_version: str
    decision_fingerprint: str
    decision_rule: str
    risk_band_before_hard_caps: str
    hard_caps_applied: list[str]


class SuitabilityDecision(BaseModel):
    risk_code: Literal["R1", "R2", "R3", "R4"]
    risk_name: str
    decision_state: DecisionState
    risk_score: int
    willingness_score: int
    capacity_score: int
    max_research_drawdown_percent: float
    per_trade_risk_budget_percent: float
    human_review_required: bool
    service_route: str
    profile_conflicts: list[str]
    explanations: list[FactorExplanation]
    allocation_envelope: list[AllocationBucket]
    stress_checks: list[StressCheck]
    required_advisor_actions: list[str]
    blocked_capabilities: list[str]
    allowed_research: list[str]
    governance: GovernanceDecision
    audit: DecisionAudit


RISK_BANDS: list[tuple[str, str, float, float]] = [
    ("R1", "保全型", 8.0, 0.35),
    ("R2", "穩健型", 12.0, 0.60),
    ("R3", "均衡型", 18.0, 1.00),
    ("R4", "成長型", 25.0, 1.25),
]

BASE_ALLOCATIONS: dict[str, list[int]] = {
    "R1": [50, 35, 15, 0],
    "R2": [35, 35, 25, 5],
    "R3": [25, 30, 35, 10],
    "R4": [20, 25, 40, 15],
}

GOAL_ADJUSTMENTS: dict[GoalPriority, list[int]] = {
    "liquidity": [10, 0, -10, 0],
    "income": [-5, 10, -5, 0],
    "growth": [-5, -5, 10, 0],
    "legacy": [5, 5, -10, 0],
}


def _normalized(value: int) -> float:
    return (value - 1) / 3 * 100


def _band_index(score: int) -> int:
    if score < 25:
        return 0
    if score < 50:
        return 1
    if score < 75:
        return 2
    return 3


def _impact(value: int, *, inverse: bool = False) -> Impact:
    effective = 5 - value if inverse else value
    if effective >= 3:
        return "supports"
    if effective <= 2:
        return "limits"
    return "neutral"


def _allocation_envelope(
    risk_code: str,
    goal_priority: GoalPriority,
    *,
    satellite_blocked: bool,
) -> list[AllocationBucket]:
    targets = [
        max(0, base + change)
        for base, change in zip(
            BASE_ALLOCATIONS[risk_code],
            GOAL_ADJUSTMENTS[goal_priority],
            strict=True,
        )
    ]
    # Keep this assertion beside the policy table so a future change cannot
    # silently emit an invalid envelope.
    if sum(targets) != 100:
        raise RuntimeError("Allocation policy must sum to 100 percent")
    if satellite_blocked and targets[3] > 0:
        targets[0] += targets[3]
        targets[3] = 0

    definitions = [
        ("流動準備", "支應家庭與企業主短期資金需求"),
        ("收益防守", "降低整體波動並建立現金流來源"),
        ("全球分散成長", "承擔經風險預算限制的長期成長曝險"),
        ("衛星策略研究", "僅容納通過研究 Gate 的有限風險部位"),
    ]
    buckets: list[AllocationBucket] = []
    for target, (name, purpose) in zip(targets, definitions, strict=True):
        width = 0 if target == 0 else 5
        buckets.append(
            AllocationBucket(
                name=name,
                target_percent=target,
                range_low_percent=max(0, target - width),
                range_high_percent=min(100, target + width),
                purpose=purpose,
            )
        )
    return buckets


def _decision_fingerprint(
    *,
    willingness_score: int,
    capacity_score: int,
    risk_code: str,
    goal_priority: GoalPriority,
    hard_caps: list[str],
) -> str:
    # Fingerprint only the already-disclosed decision facts, not the raw
    # financial profile. A keyed case-level audit ID belongs in the bank pilot.
    serialized = json.dumps(
        {
            "capacity_score": capacity_score,
            "goal_priority": goal_priority,
            "hard_caps": hard_caps,
            "model_version": MODEL_VERSION,
            "risk_code": risk_code,
            "willingness_score": willingness_score,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:20]


def _stress_checks(
    payload: SuitabilityRequest,
    risk_code: str,
) -> list[StressCheck]:
    if payload.business_dependency == 4 or (
        payload.business_dependency >= 3 and payload.income_stability <= 2
    ):
        business_state: StressState = "BLOCK"
        business_observation = "家庭收入高度依賴企業，營運中斷會直接壓縮投資承受能力。"
        business_action = "先完成緊急預備金與企業／家庭資金隔離，再討論成長部位。"
    elif payload.business_dependency == 3:
        business_state = "REVIEW"
        business_observation = "企業現金流與家庭財務仍有明顯連動。"
        business_action = "由理專確認替代收入與保險／信託緩衝安排。"
    else:
        business_state = "PASS"
        business_observation = "家庭收入對單一企業來源的依賴較低。"
        business_action = "保留年度覆核，確認依賴程度沒有顯著變化。"

    if payload.liquidity_need == 4:
        liquidity_state: StressState = "BLOCK"
        liquidity_observation = "近期資金需求高，不適合把流動資產投入高波動研究。"
        liquidity_action = "鎖住流動準備，禁止提高風險等級。"
    elif payload.liquidity_need == 3:
        liquidity_state = "REVIEW"
        liquidity_observation = "中高流動性需求可能與長期投資目標衝突。"
        liquidity_action = "確認資金使用時點並分離短、中、長期資金桶。"
    else:
        liquidity_state = "PASS"
        liquidity_observation = "目前流動性需求未形成硬性限制。"
        liquidity_action = "仍須由理專確認實際資金需求與期限。"

    if payload.wealth_concentration == 4:
        dual_state: StressState = "BLOCK"
        dual_observation = "財富高度集中，企業與市場同時承壓時可能放大單一來源風險。"
        dual_action = "優先降低集中曝險；衛星策略研究暫停。"
    elif payload.wealth_concentration >= 3 or risk_code in {"R3", "R4"}:
        dual_state = "REVIEW"
        dual_observation = "雙重壓力情境需要額外檢視集中度與最大回撤。"
        dual_action = "理專須檢視壓力測試與研究 Gate 證據後才能放行。"
    else:
        dual_state = "PASS"
        dual_observation = "集中度與研究風險目前落在保守邊界內。"
        dual_action = "持續監測集中度，不代表任何商品已通過適合度審查。"

    return [
        StressCheck(
            scenario="企業現金流中斷",
            state=business_state,
            observation=business_observation,
            advisor_action=business_action,
        ),
        StressCheck(
            scenario="短期資金需求上升",
            state=liquidity_state,
            observation=liquidity_observation,
            advisor_action=liquidity_action,
        ),
        StressCheck(
            scenario="企業與市場雙重承壓",
            state=dual_state,
            observation=dual_observation,
            advisor_action=dual_action,
        ),
    ]


@router.post(
    "/suitability",
    response_model=SuitabilityDecision,
    summary="競賽原型：企業主雙軸適合度與研究邊界決策",
)
def suitability(payload: SuitabilityRequest) -> SuitabilityDecision:
    willingness_score = round(
        _normalized(payload.loss_tolerance) * 0.45
        + _normalized(payload.investment_horizon) * 0.30
        + _normalized(payload.investment_experience) * 0.25
    )
    capacity_score = round(
        _normalized(5 - payload.liquidity_need) * 0.30
        + _normalized(payload.income_stability) * 0.20
        + _normalized(5 - payload.business_dependency) * 0.25
        + _normalized(5 - payload.wealth_concentration) * 0.25
    )

    willingness_band = _band_index(willingness_score)
    capacity_band = _band_index(capacity_score)
    pre_cap_band = min(willingness_band, capacity_band)
    hard_caps: list[tuple[int, str]] = []

    if payload.loss_tolerance == 1:
        hard_caps.append((0, "可承受虧損極低：最高 R1"))
    if payload.liquidity_need == 4:
        hard_caps.append((0, "近期流動性需求高：最高 R1"))
    if payload.investment_horizon == 1:
        hard_caps.append((1, "投資期限未滿一年：最高 R2"))
    if payload.investment_experience == 1:
        hard_caps.append((1, "缺乏投資經驗：最高 R2"))
    if payload.business_dependency >= 3 and payload.wealth_concentration >= 3:
        hard_caps.append((1, "企業依賴與財富集中同時偏高：最高 R2"))

    final_band = pre_cap_band
    if hard_caps:
        final_band = min(final_band, *(cap for cap, _ in hard_caps))

    risk_code, risk_name, max_drawdown, risk_budget = RISK_BANDS[final_band]
    pre_cap_code = RISK_BANDS[pre_cap_band][0]
    hard_cap_reasons = [reason for _, reason in hard_caps]
    satellite_blocked = (
        payload.investment_horizon == 1
        or payload.liquidity_need == 4
        or payload.investment_experience == 1
        or payload.business_dependency == 4
        or payload.wealth_concentration == 4
    )

    conflicts: list[str] = []
    if willingness_score - capacity_score >= 25:
        conflicts.append("願意承擔的風險高於實際承受能力，採較低的承受能力等級。")
    if payload.goal_priority == "growth" and risk_code in {"R1", "R2"}:
        conflicts.append("成長目標與目前風險容量不一致，不提高等級，只調整理財討論順序。")
    if payload.business_dependency >= 3:
        conflicts.append("家庭收入與企業營運連動，必須先檢視企業現金流風險。")
    if payload.wealth_concentration >= 3:
        conflicts.append("財富來源集中，新增研究部位不得再強化同一風險來源。")

    explanations = [
        FactorExplanation(
            factor="虧損承受意願",
            impact=_impact(payload.loss_tolerance),
            explanation="只影響投資意願；不能抵銷流動性或企業集中等容量限制。",
        ),
        FactorExplanation(
            factor="投資期限",
            impact=_impact(payload.investment_horizon),
            explanation="期限越長，越能容納市場波動；未滿一年會觸發硬性上限。",
        ),
        FactorExplanation(
            factor="流動性需求",
            impact=_impact(payload.liquidity_need, inverse=True),
            explanation="近期資金需求越高，可承擔的投資波動越低。",
        ),
        FactorExplanation(
            factor="投資經驗",
            impact=_impact(payload.investment_experience),
            explanation="經驗不足時限制複雜與高波動研究，不以問卷高分放寬。",
        ),
        FactorExplanation(
            factor="收入穩定度",
            impact=_impact(payload.income_stability),
            explanation="穩定替代收入有助承受企業分紅或現金流中斷。",
        ),
        FactorExplanation(
            factor="企業收入依賴",
            impact=_impact(payload.business_dependency, inverse=True),
            explanation="企業依賴越高，家庭與事業同時承壓的風險越大。",
        ),
        FactorExplanation(
            factor="財富集中度",
            impact=_impact(payload.wealth_concentration, inverse=True),
            explanation="財富集中於企業或單一來源時，新增風險必須更保守。",
        ),
    ]

    advisor_actions = [
        "確認銀行既有 KYC／適合度資料與本次粗粒度輪廓是否一致。",
        "針對所有 REVIEW／BLOCK 壓力情境留下人工覆核紀錄。",
        "只查看符合此風險邊界且通過 Research Gate 的研究證據。",
    ]
    if conflicts:
        advisor_actions.insert(0, "先處理輪廓衝突，不直接進入商品推介。")

    return SuitabilityDecision(
        risk_code=risk_code,
        risk_name=risk_name,
        decision_state=(
            "REVIEW_REQUIRED" if conflicts or hard_caps else "RESEARCH_ALLOWED"
        ),
        risk_score=min(willingness_score, capacity_score),
        willingness_score=willingness_score,
        capacity_score=capacity_score,
        max_research_drawdown_percent=max_drawdown,
        per_trade_risk_budget_percent=risk_budget,
        human_review_required=True,
        service_route=(
            "先處理企業／家庭風險衝突，再由理專覆核"
            if conflicts or hard_caps
            else "進入受限研究，仍須由理專覆核"
        ),
        profile_conflicts=conflicts,
        explanations=explanations,
        allocation_envelope=_allocation_envelope(
            risk_code,
            payload.goal_priority,
            satellite_blocked=satellite_blocked,
        ),
        stress_checks=_stress_checks(payload, risk_code),
        required_advisor_actions=advisor_actions,
        blocked_capabilities=[
            "自動下單",
            "付款或資金移轉",
            "把研究候選直接當成個別商品建議",
            "繞過 Final Holdout 或人工覆核",
            "未通過研究 Gate 的對客發布",
        ],
        allowed_research=[
            f"{risk_code} 邊界內的市場與策略研究",
            "匿名輪廓的可解釋風險摘要",
            "企業／家庭雙重壓力情境檢查",
            "提供理專人工覆核的研究證據包",
        ],
        governance=GovernanceDecision(
            pii_collected=False,
            exact_balance_collected=False,
            prototype_persists_profile=False,
            extra_fields_rejected=True,
            execution_authority=False,
            payment_authority=False,
            final_holdout_interactive_access=False,
            human_review_required=True,
            fail_closed=True,
        ),
        audit=DecisionAudit(
            model_version=MODEL_VERSION,
            decision_fingerprint=_decision_fingerprint(
                willingness_score=willingness_score,
                capacity_score=capacity_score,
                risk_code=risk_code,
                goal_priority=payload.goal_priority,
                hard_caps=hard_cap_reasons,
            ),
            decision_rule="lower_of_willingness_and_capacity_then_hard_caps",
            risk_band_before_hard_caps=pre_cap_code,
            hard_caps_applied=hard_cap_reasons,
        ),
    )
