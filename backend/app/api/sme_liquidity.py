from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.services.sme_liquidity import (
    LiquidityProfile,
    Payable,
    Receivable,
    forecast_liquidity,
)

router = APIRouter()


class ReceivableInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float = Field(gt=0, le=10_000_000_000)
    due_day: int = Field(ge=1, le=180)
    delay_mean_days: float = Field(default=5.0, ge=0, le=120)
    delay_std_days: float = Field(default=5.0, ge=0, le=120)
    default_probability: float = Field(default=0.01, ge=0, le=1)


class PayableInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount: float = Field(gt=0, le=10_000_000_000)
    due_day: int = Field(ge=1, le=180)


class LiquidityForecastRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(default="", max_length=80)
    industry: str = Field(default="", max_length=80)
    description: str = Field(default="", max_length=300)

    current_cash: float = Field(ge=0, le=100_000_000_000)
    safety_cash_floor: float = Field(ge=0, le=100_000_000_000)
    baseline_daily_inflow: float = Field(ge=0, le=10_000_000_000)
    daily_inflow_volatility: float = Field(ge=0, le=10_000_000_000)
    fixed_daily_outflow: float = Field(ge=0, le=10_000_000_000)
    payroll_amount: float = Field(ge=0, le=100_000_000_000)
    payroll_every_days: int = Field(ge=1, le=90)
    fx_receivable_share: float = Field(default=0.0, ge=0, le=1)

    receivables: list[ReceivableInput] = Field(default_factory=list, max_length=100)
    payables: list[PayableInput] = Field(default_factory=list, max_length=100)

    simulations: int = Field(default=2500, ge=500, le=20_000)
    seed: int = Field(default=20260827, ge=0, le=2_147_483_647)

    @model_validator(mode="after")
    def validate_profile(self) -> "LiquidityForecastRequest":
        if self.safety_cash_floor > 100_000_000_000:
            raise ValueError("safety cash floor out of range")
        if self.baseline_daily_inflow == 0 and self.daily_inflow_volatility > 0:
            raise ValueError("daily inflow volatility must be zero when mean inflow is zero")
        return self


@router.post("/forecast")
def forecast(request: LiquidityForecastRequest) -> dict[str, object]:
    profile = LiquidityProfile(
        name=request.name.strip(),
        industry=request.industry.strip(),
        description=request.description.strip(),
        current_cash=request.current_cash,
        safety_cash_floor=request.safety_cash_floor,
        baseline_daily_inflow=request.baseline_daily_inflow,
        daily_inflow_volatility=request.daily_inflow_volatility,
        fixed_daily_outflow=request.fixed_daily_outflow,
        payroll_amount=request.payroll_amount,
        payroll_every_days=request.payroll_every_days,
        receivables=tuple(
            Receivable(
                amount=item.amount,
                due_day=item.due_day,
                delay_mean_days=item.delay_mean_days,
                delay_std_days=item.delay_std_days,
                default_probability=item.default_probability,
            )
            for item in request.receivables
        ),
        payables=tuple(
            Payable(amount=item.amount, due_day=item.due_day)
            for item in request.payables
        ),
        fx_receivable_share=request.fx_receivable_share,
    )

    return forecast_liquidity(
        profile,
        simulations=request.simulations,
        seed=request.seed,
    )
