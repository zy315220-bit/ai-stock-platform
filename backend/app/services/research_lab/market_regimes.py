from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Callable

import pandas as pd

from app.services.backtest.corporate_action_gate import prepare_research_frame
from app.services.backtest.engine import _download_backtest_history
from corporate_actions import dividends_by_ex_date

from .causal_regimes import estimate_hamilton_regime_as_of
from .models import ResearchCandidate, ResearchSplit
from .runner import BacktestFn, _ALLOWED_PARAMETERS, _validation_metrics
from .scoring import wilson_lower_bound


class MarketRegime(str, Enum):
    BULL = "BULL"
    BEAR = "BEAR"
    SIDEWAYS = "SIDEWAYS"


@dataclass(frozen=True)
class RegimeSlice:
    slice_id: str
    start_date: str
    end_date: str


@dataclass(frozen=True)
class MarketRegimeMatrix:
    candidate_id: str
    benchmark_code: str
    slices: tuple[dict[str, Any], ...]
    by_regime: dict[str, dict[str, Any]]
    robustness: dict[str, Any]
    data_fingerprints: tuple[str, ...] = ()


RegimeLabelFn = Callable[
    [RegimeSlice],
    tuple[MarketRegime, dict[str, Any]],
]


def classify_market_regime(
    benchmark_return_percent: float,
    *,
    bull_threshold_percent: float = 5.0,
    bear_threshold_percent: float = -5.0,
) -> MarketRegime:
    """Classify a completed evaluation slice from benchmark performance.

    This label is post-hoc audit metadata. It is never available to the trading
    rule while orders are generated, so it cannot become a look-ahead signal.
    """
    if benchmark_return_percent >= bull_threshold_percent:
        return MarketRegime.BULL
    if benchmark_return_percent <= bear_threshold_percent:
        return MarketRegime.BEAR
    return MarketRegime.SIDEWAYS


def load_point_in_time_benchmark_returns(
    benchmark_code: str,
    split: ResearchSplit,
) -> pd.Series:
    """Load a split-safe total-return series for causal regime estimation."""
    required_start = (
        pd.Timestamp(split.train_start) - pd.DateOffset(years=3)
    ).strftime("%Y-%m-%d")
    frame = _download_backtest_history(
        benchmark_code,
        required_start_date=required_start,
        required_end_date=split.validation_end,
    )
    frame = prepare_research_frame(frame, benchmark_code)
    if "Date" in frame.columns:
        dates = pd.to_datetime(frame["Date"], errors="coerce")
        closes = pd.Series(
            pd.to_numeric(frame["Close"], errors="coerce").to_numpy(),
            index=dates,
            dtype=float,
        )
    else:
        closes = pd.Series(
            pd.to_numeric(frame["Close"], errors="coerce").to_numpy(),
            index=pd.to_datetime(frame.index, errors="coerce"),
            dtype=float,
        )
    closes = closes.dropna().sort_index()
    returns = closes.pct_change().dropna()
    dividend_events = dividends_by_ex_date(frame)
    for event_date, amount in dividend_events.items():
        timestamp = pd.Timestamp(event_date).normalize()
        prior = closes.loc[closes.index < timestamp]
        if prior.empty or timestamp not in returns.index:
            continue
        returns.loc[timestamp] += float(amount) / float(prior.iloc[-1])
    returns = returns.sort_index()
    digest = hashlib.sha256()
    digest.update(b"causal-regime-total-return-series-v1")
    digest.update(benchmark_code.strip().upper().encode("utf-8"))
    digest.update(
        pd.util.hash_pandas_object(
            returns,
            index=True,
            categorize=True,
        ).to_numpy(dtype="uint64", copy=False).tobytes()
    )
    digest.update(
        json.dumps(
            {
                "price_basis": frame.attrs.get("price_basis"),
                "split_adjustments": frame.attrs.get(
                    "split_adjustments",
                    [],
                ),
                "dividends": frame.attrs.get("dividends", []),
                "corporate_action_catalog_revision": frame.attrs.get(
                    "corporate_action_catalog_revision"
                ),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
    )
    returns.attrs["data_fingerprint"] = digest.hexdigest()[:20]
    returns.attrs["benchmark_code"] = benchmark_code.strip().upper()
    returns.attrs["price_basis"] = frame.attrs.get("price_basis")
    return returns


def build_pre_holdout_regime_slices(
    split: ResearchSplit,
    *,
    slice_count: int = 6,
) -> tuple[RegimeSlice, ...]:
    """Cover development plus validation while excluding final holdout."""
    if slice_count < 3:
        raise ValueError("regime slice_count must be at least 3")
    start = pd.Timestamp(split.train_start).normalize()
    end = pd.Timestamp(split.validation_end).normalize()
    if start >= end:
        raise ValueError("pre-holdout range must contain multiple dates")

    boundaries = pd.date_range(
        start=start,
        end=end + pd.Timedelta(days=1),
        periods=slice_count + 1,
    )
    slices: list[RegimeSlice] = []
    for index in range(slice_count):
        slice_start = boundaries[index].normalize()
        slice_end = (
            boundaries[index + 1] - pd.Timedelta(days=1)
        ).normalize()
        if index == slice_count - 1:
            slice_end = end
        if slice_end < slice_start:
            continue
        slices.append(
            RegimeSlice(
                slice_id=f"R{index + 1}",
                start_date=slice_start.strftime("%Y-%m-%d"),
                end_date=slice_end.strftime("%Y-%m-%d"),
            )
        )
    return tuple(slices)


def _benchmark_return(report: dict[str, Any]) -> float:
    buy_and_hold = report.get("buy_and_hold") or {}
    value = buy_and_hold.get(
        "return_percent",
        report.get("benchmark_return_percent", report.get("total_return_percent", 0.0)),
    )
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _aggregate_regime_rows(
    rows: list[dict[str, Any]],
    *,
    min_completed_trades_per_regime: int,
    max_drawdown_percent: float,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_regime: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []
    required = (MarketRegime.BULL.value, MarketRegime.BEAR.value)

    for regime in MarketRegime:
        selected = [row for row in rows if row["market_regime"] == regime.value]
        slice_count = len(selected)
        completed = sum(int(row["completed_trades"]) for row in selected)
        wins = sum(int(row["winning_trades"]) for row in selected)
        denominator = max(1, slice_count)
        mean_return = sum(
            float(row["total_return_percent"]) for row in selected
        ) / denominator
        mean_benchmark = sum(
            float(row["benchmark_return_percent"]) for row in selected
        ) / denominator
        mean_alpha = sum(
            float(row["alpha_percent"]) for row in selected
        ) / denominator
        worst_drawdown = max(
            (
                abs(float(row["max_drawdown_percent"]))
                for row in selected
            ),
            default=0.0,
        )
        positive_alpha_slices = sum(
            float(row["alpha_percent"]) >= 0 for row in selected
        )
        wilson_percent = wilson_lower_bound(wins, completed) * 100.0
        by_regime[regime.value] = {
            "slice_count": slice_count,
            "completed_trades": completed,
            "winning_trades": wins,
            "win_rate_percent": round(
                wins / completed * 100.0 if completed else 0.0,
                4,
            ),
            "wilson_win_rate_lower_bound_percent": round(
                wilson_percent,
                4,
            ),
            "mean_return_percent": round(mean_return, 4),
            "mean_benchmark_return_percent": round(mean_benchmark, 4),
            "mean_alpha_percent": round(mean_alpha, 4),
            "positive_alpha_slice_ratio": round(
                positive_alpha_slices / denominator,
                4,
            ),
            "worst_drawdown_percent": round(worst_drawdown, 4),
        }

    for regime in required:
        item = by_regime[regime]
        if item["slice_count"] == 0:
            reasons.append(f"missing_{regime.lower()}_regime")
            continue
        if item["completed_trades"] < min_completed_trades_per_regime:
            reasons.append(f"insufficient_{regime.lower()}_trades")
        if item["mean_return_percent"] < 0:
            reasons.append(f"negative_{regime.lower()}_return")
        if item["mean_alpha_percent"] < 0:
            reasons.append(f"negative_{regime.lower()}_alpha")
        if item["worst_drawdown_percent"] > max_drawdown_percent:
            reasons.append(f"{regime.lower()}_drawdown_too_high")

    required_items = [by_regime[name] for name in required]
    conservative_wilson = min(
        (
            float(item["wilson_win_rate_lower_bound_percent"])
            for item in required_items
            if item["slice_count"] > 0
        ),
        default=0.0,
    )
    conservative_return = min(
        (
            float(item["mean_return_percent"])
            for item in required_items
            if item["slice_count"] > 0
        ),
        default=-100.0,
    )
    conservative_alpha = min(
        (
            float(item["mean_alpha_percent"])
            for item in required_items
            if item["slice_count"] > 0
        ),
        default=-100.0,
    )
    worst_required_drawdown = max(
        (
            float(item["worst_drawdown_percent"])
            for item in required_items
        ),
        default=0.0,
    )
    robustness_score = (
        35.0 * max(0.0, min(conservative_wilson / 60.0, 1.0))
        + 30.0 * max(-1.0, min(conservative_return / 15.0, 1.0))
        + 25.0 * max(-1.0, min(conservative_alpha / 15.0, 1.0))
        + 10.0
        * max(0.0, 1.0 - worst_required_drawdown / max_drawdown_percent)
    )
    robustness = {
        "robust_across_required_regimes": not reasons,
        "required_regimes": list(required),
        "minimum_completed_trades_per_regime": (
            min_completed_trades_per_regime
        ),
        "maximum_drawdown_percent": max_drawdown_percent,
        "conservative_wilson_lower_bound_percent": round(
            conservative_wilson,
            4,
        ),
        "conservative_return_percent": round(conservative_return, 4),
        "conservative_alpha_percent": round(conservative_alpha, 4),
        "robustness_score": round(robustness_score, 4),
        "reasons": reasons,
        "holdout_used": False,
        "regime_labels_point_in_time": True,
        "regime_labels_are_trading_signals": False,
    }
    return by_regime, robustness


def run_market_regime_validation(
    stock_code: str,
    split: ResearchSplit,
    candidate: ResearchCandidate,
    *,
    backtest_fn: BacktestFn,
    benchmark_backtest_fn: BacktestFn | None = None,
    benchmark_code: str = "0050",
    slice_count: int = 6,
    min_completed_trades_per_regime: int = 3,
    max_drawdown_percent: float = 30.0,
    benchmark_cache: dict[tuple[str, str], dict[str, Any]] | None = None,
    regime_estimate_cache: dict[
        str,
        tuple[MarketRegime, dict[str, Any]],
    ] | None = None,
    regime_return_series: pd.Series | None = None,
    regime_label_fn: RegimeLabelFn | None = None,
) -> MarketRegimeMatrix:
    """Audit one candidate across causally labelled market-regime slices."""
    unknown = set(candidate.parameters) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(f"Unsupported research parameters: {sorted(unknown)}")
    benchmark_fn = benchmark_backtest_fn or backtest_fn
    cache = benchmark_cache if benchmark_cache is not None else {}
    estimate_cache = (
        regime_estimate_cache
        if regime_estimate_cache is not None
        else {}
    )
    rows: list[dict[str, Any]] = []
    data_fingerprints: set[str] = set()
    causal_returns = regime_return_series
    if regime_label_fn is None and causal_returns is None:
        causal_returns = load_point_in_time_benchmark_returns(
            benchmark_code,
            split,
        )
    if causal_returns is not None:
        causal_fingerprint = causal_returns.attrs.get("data_fingerprint")
        if causal_fingerprint:
            data_fingerprints.add(str(causal_fingerprint))

    for regime_slice in build_pre_holdout_regime_slices(
        split,
        slice_count=slice_count,
    ):
        report = backtest_fn(
            stock_code=stock_code,
            start_date=regime_slice.start_date,
            end_date=regime_slice.end_date,
            liquidate_at_end=False,
            **candidate.parameters,
        )
        metrics = _validation_metrics(report)
        cache_key = (regime_slice.start_date, regime_slice.end_date)
        if stock_code.strip().upper() == benchmark_code.strip().upper():
            benchmark_report = report
        elif cache_key in cache:
            benchmark_report = cache[cache_key]
        else:
            benchmark_report = benchmark_fn(
                stock_code=benchmark_code,
                start_date=regime_slice.start_date,
                end_date=regime_slice.end_date,
                entry_score=99,
                exit_score=1,
                initial_capital=float(
                    candidate.parameters.get("initial_capital", 1_000_000.0)
                ),
                liquidate_at_end=True,
            )
            cache[cache_key] = benchmark_report

        benchmark_return = _benchmark_return(benchmark_report)
        strategy_fingerprint = metrics.get("data_fingerprint")
        benchmark_fingerprint = _validation_metrics(
            benchmark_report
        ).get("data_fingerprint")
        if strategy_fingerprint:
            data_fingerprints.add(str(strategy_fingerprint))
        if benchmark_fingerprint:
            data_fingerprints.add(str(benchmark_fingerprint))
        strategy_return = float(
            metrics.get("total_return_percent", 0.0) or 0.0
        )
        completed = int(metrics.get("completed_trades", 0) or 0)
        winning = int(metrics.get("winning_trades", 0) or 0)
        if regime_label_fn is not None:
            regime, regime_audit = regime_label_fn(regime_slice)
        else:
            if causal_returns is None:
                raise ValueError("Point-in-time regime returns are unavailable")
            estimate_key = regime_slice.start_date
            cached_estimate = estimate_cache.get(estimate_key)
            if cached_estimate is None:
                as_of_date = (
                    pd.Timestamp(regime_slice.start_date)
                    - pd.Timedelta(days=1)
                )
                estimate = estimate_hamilton_regime_as_of(
                    causal_returns,
                    as_of_date,
                )
                cached_estimate = (
                    MarketRegime(estimate.regime),
                    estimate.to_dict(),
                )
                estimate_cache[estimate_key] = cached_estimate
            regime, regime_audit = cached_estimate
        rows.append(
            {
                **asdict(regime_slice),
                "market_regime": regime.value,
                "regime_as_of_date": regime_audit.get("as_of_date"),
                "regime_method": regime_audit.get("method"),
                "regime_confidence": regime_audit.get("confidence"),
                "regime_audit": regime_audit,
                "benchmark_code": benchmark_code,
                "strategy_data_fingerprint": strategy_fingerprint,
                "benchmark_data_fingerprint": benchmark_fingerprint,
                "benchmark_return_percent": round(benchmark_return, 4),
                "total_return_percent": round(strategy_return, 4),
                "alpha_percent": round(
                    strategy_return - benchmark_return,
                    4,
                ),
                "completed_trades": completed,
                "winning_trades": winning,
                "win_rate_percent": round(
                    winning / completed * 100.0 if completed else 0.0,
                    4,
                ),
                "wilson_win_rate_lower_bound_percent": round(
                    wilson_lower_bound(winning, completed) * 100.0,
                    4,
                ),
                "max_drawdown_percent": round(
                    abs(
                        float(
                            metrics.get("max_drawdown_percent", 0.0)
                            or 0.0
                        )
                    ),
                    4,
                ),
                "open_position_count": int(
                    metrics.get("open_position_count", 0) or 0
                ),
            }
        )

    by_regime, robustness = _aggregate_regime_rows(
        rows,
        min_completed_trades_per_regime=(
            min_completed_trades_per_regime
        ),
        max_drawdown_percent=max_drawdown_percent,
    )
    return MarketRegimeMatrix(
        candidate_id=candidate.candidate_id,
        benchmark_code=benchmark_code,
        slices=tuple(rows),
        by_regime=by_regime,
        robustness=robustness,
        data_fingerprints=tuple(sorted(data_fingerprints)),
    )
