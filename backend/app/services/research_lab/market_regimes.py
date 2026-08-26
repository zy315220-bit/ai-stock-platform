from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
import hashlib
import json
from typing import Any, Callable

import pandas as pd

from app.services.backtest.corporate_action_gate import prepare_research_frame
from app.services.backtest.engine import (
    InsufficientBacktestHistoryError,
    _download_backtest_history,
)
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


_REQUIRED_REGIMES = (MarketRegime.BULL.value, MarketRegime.BEAR.value)
_DEFAULT_EXTENSION_STEP_YEARS = 2
_DEFAULT_MAX_EXTENSION_YEARS = 10


def classify_market_regime(
    benchmark_return_percent: float,
    *,
    bull_threshold_percent: float = 5.0,
    bear_threshold_percent: float = -5.0,
) -> MarketRegime:
    """Classify a completed slice from benchmark performance for audit use."""
    if benchmark_return_percent >= bull_threshold_percent:
        return MarketRegime.BULL
    if benchmark_return_percent <= bear_threshold_percent:
        return MarketRegime.BEAR
    return MarketRegime.SIDEWAYS


def load_point_in_time_benchmark_returns(
    benchmark_code: str,
    split: ResearchSplit,
    *,
    max_extension_years: int = _DEFAULT_MAX_EXTENSION_YEARS,
) -> pd.Series:
    """Load enough pre-holdout benchmark history for causal regime discovery.

    The extra history is used only by the regime stress test. It never enters
    Train memory, Validation feedback, or Final Holdout.
    """
    required_start = (
        pd.Timestamp(split.train_start)
        - pd.DateOffset(years=max(0, int(max_extension_years)) + 3)
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
    for event_date, amount in dividends_by_ex_date(frame).items():
        timestamp = pd.Timestamp(event_date).normalize()
        prior = closes.loc[closes.index < timestamp]
        if prior.empty or timestamp not in returns.index:
            continue
        returns.loc[timestamp] += float(amount) / float(prior.iloc[-1])
    returns = returns.sort_index()

    digest = hashlib.sha256()
    digest.update(b"causal-regime-total-return-series-v2-extended")
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
                "split_adjustments": frame.attrs.get("split_adjustments", []),
                "dividends": frame.attrs.get("dividends", []),
                "corporate_action_catalog_revision": frame.attrs.get(
                    "corporate_action_catalog_revision"
                ),
                "max_extension_years": max(0, int(max_extension_years)),
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


def _build_regime_slices_for_window(
    start: pd.Timestamp,
    end: pd.Timestamp,
    *,
    slice_count: int,
) -> tuple[RegimeSlice, ...]:
    if slice_count < 3:
        raise ValueError("regime slice_count must be at least 3")
    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()
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
        slice_end = (boundaries[index + 1] - pd.Timedelta(days=1)).normalize()
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


def build_pre_holdout_regime_slices(
    split: ResearchSplit,
    *,
    slice_count: int = 6,
) -> tuple[RegimeSlice, ...]:
    """Cover Train + Validation while excluding Final Holdout."""
    return _build_regime_slices_for_window(
        pd.Timestamp(split.train_start),
        pd.Timestamp(split.validation_end),
        slice_count=slice_count,
    )


def _benchmark_return(report: dict[str, Any]) -> float:
    buy_and_hold = report.get("buy_and_hold") or {}
    value = buy_and_hold.get(
        "return_percent",
        report.get(
            "benchmark_return_percent",
            report.get("total_return_percent", 0.0),
        ),
    )
    try:
        return float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0


def _label_slices(
    slices: tuple[RegimeSlice, ...],
    *,
    causal_returns: pd.Series,
    estimate_cache: dict[str, tuple[MarketRegime, dict[str, Any]]],
) -> list[tuple[RegimeSlice, MarketRegime, dict[str, Any]]]:
    labelled: list[tuple[RegimeSlice, MarketRegime, dict[str, Any]]] = []
    for regime_slice in slices:
        key = regime_slice.start_date
        cached = estimate_cache.get(key)
        if cached is None:
            as_of_date = pd.Timestamp(regime_slice.start_date) - pd.Timedelta(days=1)
            estimate = estimate_hamilton_regime_as_of(causal_returns, as_of_date)
            cached = (MarketRegime(estimate.regime), estimate.to_dict())
            estimate_cache[key] = cached
        labelled.append((regime_slice, cached[0], cached[1]))
    return labelled


def _adaptive_labelled_slices(
    split: ResearchSplit,
    *,
    slice_count: int,
    causal_returns: pd.Series,
    estimate_cache: dict[str, tuple[MarketRegime, dict[str, Any]]],
    extension_step_years: int,
    max_extension_years: int,
) -> tuple[
    list[tuple[RegimeSlice, MarketRegime, dict[str, Any]]],
    int,
    tuple[str, ...],
]:
    """Extend only when the base window cannot observe all required regimes.

    Slice density is preserved as the window grows so extending the horizon does
    not turn each slice into a multi-year block that can hide regime changes.
    """
    original_start = pd.Timestamp(split.train_start).normalize()
    end = pd.Timestamp(split.validation_end).normalize()
    base_span_days = max(1, (end - original_start).days)
    step = max(1, int(extension_step_years))
    cap = max(0, int(max_extension_years))
    last_missing: tuple[str, ...] = _REQUIRED_REGIMES

    for extension_years in range(0, cap + 1, step):
        start = original_start - pd.DateOffset(years=extension_years)
        span_days = max(1, (end - start).days)
        scaled_count = max(
            slice_count,
            round(slice_count * span_days / base_span_days),
        )
        slices = _build_regime_slices_for_window(
            start,
            end,
            slice_count=scaled_count,
        )
        labelled = _label_slices(
            slices,
            causal_returns=causal_returns,
            estimate_cache=estimate_cache,
        )
        observed = {regime.value for _, regime, _ in labelled}
        missing = tuple(name for name in _REQUIRED_REGIMES if name not in observed)
        if not missing:
            return labelled, extension_years, ()
        last_missing = missing

    return labelled, cap, last_missing


def _aggregate_regime_rows(
    rows: list[dict[str, Any]],
    *,
    min_completed_trades_per_regime: int,
    max_drawdown_percent: float,
) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    by_regime: dict[str, dict[str, Any]] = {}
    reasons: list[str] = []

    for regime in MarketRegime:
        labelled = [row for row in rows if row["market_regime"] == regime.value]
        selected = [row for row in labelled if row.get("evidence_available", True)]
        slice_count = len(selected)
        unavailable_slice_count = len(labelled) - slice_count
        completed = sum(int(row["completed_trades"]) for row in selected)
        wins = sum(int(row["winning_trades"]) for row in selected)
        denominator = max(1, slice_count)
        mean_return = sum(float(row["total_return_percent"]) for row in selected) / denominator
        mean_benchmark = sum(float(row["benchmark_return_percent"]) for row in selected) / denominator
        mean_alpha = sum(float(row["alpha_percent"]) for row in selected) / denominator
        worst_drawdown = max(
            (abs(float(row["max_drawdown_percent"])) for row in selected),
            default=0.0,
        )
        positive_alpha_slices = sum(float(row["alpha_percent"]) >= 0 for row in selected)
        wilson_percent = wilson_lower_bound(wins, completed) * 100.0
        by_regime[regime.value] = {
            "labelled_slice_count": len(labelled),
            "slice_count": slice_count,
            "unavailable_slice_count": unavailable_slice_count,
            "completed_trades": completed,
            "winning_trades": wins,
            "win_rate_percent": round(wins / completed * 100.0 if completed else 0.0, 4),
            "wilson_win_rate_lower_bound_percent": round(wilson_percent, 4),
            "mean_return_percent": round(mean_return, 4),
            "mean_benchmark_return_percent": round(mean_benchmark, 4),
            "mean_alpha_percent": round(mean_alpha, 4),
            "positive_alpha_slice_ratio": round(positive_alpha_slices / denominator, 4),
            "worst_drawdown_percent": round(worst_drawdown, 4),
        }

    unavailable_slice_count = sum(
        int(item["unavailable_slice_count"]) for item in by_regime.values()
    )
    if unavailable_slice_count:
        reasons.append("insufficient_regime_slice_history")

    for regime in _REQUIRED_REGIMES:
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

    required_items = [by_regime[name] for name in _REQUIRED_REGIMES]
    conservative_wilson = min(
        (float(item["wilson_win_rate_lower_bound_percent"]) for item in required_items if item["slice_count"] > 0),
        default=0.0,
    )
    conservative_return = min(
        (float(item["mean_return_percent"]) for item in required_items if item["slice_count"] > 0),
        default=-100.0,
    )
    conservative_alpha = min(
        (float(item["mean_alpha_percent"]) for item in required_items if item["slice_count"] > 0),
        default=-100.0,
    )
    worst_required_drawdown = max(
        (float(item["worst_drawdown_percent"]) for item in required_items),
        default=0.0,
    )
    robustness_score = (
        35.0 * max(0.0, min(conservative_wilson / 60.0, 1.0))
        + 30.0 * max(-1.0, min(conservative_return / 15.0, 1.0))
        + 25.0 * max(-1.0, min(conservative_alpha / 15.0, 1.0))
        + 10.0 * max(0.0, 1.0 - worst_required_drawdown / max_drawdown_percent)
    )
    return by_regime, {
        "robust_across_required_regimes": not reasons,
        "required_regimes": list(_REQUIRED_REGIMES),
        "minimum_completed_trades_per_regime": min_completed_trades_per_regime,
        "maximum_drawdown_percent": max_drawdown_percent,
        "conservative_wilson_lower_bound_percent": round(conservative_wilson, 4),
        "conservative_return_percent": round(conservative_return, 4),
        "conservative_alpha_percent": round(conservative_alpha, 4),
        "robustness_score": round(robustness_score, 4),
        "reasons": reasons,
        "unavailable_slice_count": unavailable_slice_count,
        "holdout_used": False,
        "regime_labels_point_in_time": True,
        "regime_labels_are_trading_signals": False,
    }


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
    regime_estimate_cache: dict[str, tuple[MarketRegime, dict[str, Any]]] | None = None,
    regime_return_series: pd.Series | None = None,
    regime_label_fn: RegimeLabelFn | None = None,
    extension_step_years: int = _DEFAULT_EXTENSION_STEP_YEARS,
    max_extension_years: int = _DEFAULT_MAX_EXTENSION_YEARS,
) -> MarketRegimeMatrix:
    """Audit a candidate and extend history if the base window misses a regime."""
    unknown = set(candidate.parameters) - _ALLOWED_PARAMETERS
    if unknown:
        raise ValueError(f"Unsupported research parameters: {sorted(unknown)}")

    benchmark_fn = benchmark_backtest_fn or backtest_fn
    cache = benchmark_cache if benchmark_cache is not None else {}
    estimate_cache = regime_estimate_cache if regime_estimate_cache is not None else {}
    data_fingerprints: set[str] = set()
    causal_returns = regime_return_series
    if regime_label_fn is None and causal_returns is None:
        causal_returns = load_point_in_time_benchmark_returns(
            benchmark_code,
            split,
            max_extension_years=max_extension_years,
        )
    if causal_returns is not None:
        causal_fingerprint = causal_returns.attrs.get("data_fingerprint")
        if causal_fingerprint:
            data_fingerprints.add(str(causal_fingerprint))

    if regime_label_fn is not None:
        labelled_slices = [
            (item, *regime_label_fn(item))
            for item in build_pre_holdout_regime_slices(split, slice_count=slice_count)
        ]
        extension_years = 0
        missing_after_extension: tuple[str, ...] = ()
    else:
        if causal_returns is None:
            raise ValueError("Point-in-time regime returns are unavailable")
        labelled_slices, extension_years, missing_after_extension = _adaptive_labelled_slices(
            split,
            slice_count=slice_count,
            causal_returns=causal_returns,
            estimate_cache=estimate_cache,
            extension_step_years=extension_step_years,
            max_extension_years=max_extension_years,
        )

    rows: list[dict[str, Any]] = []
    for regime_slice, regime, regime_audit in labelled_slices:
        try:
            report = backtest_fn(
                stock_code=stock_code,
                start_date=regime_slice.start_date,
                end_date=regime_slice.end_date,
                liquidate_at_end=False,
                **candidate.parameters,
            )
        except InsufficientBacktestHistoryError as exc:
            rows.append(
                {
                    **asdict(regime_slice),
                    "market_regime": regime.value,
                    "regime_as_of_date": regime_audit.get("as_of_date"),
                    "regime_method": regime_audit.get("method"),
                    "regime_confidence": regime_audit.get("confidence"),
                    "regime_audit": regime_audit,
                    "benchmark_code": benchmark_code,
                    "evidence_available": False,
                    "evidence_reason": "insufficient_indicator_history",
                    "evidence_detail": str(exc),
                    "strategy_data_fingerprint": None,
                    "benchmark_data_fingerprint": None,
                    "benchmark_return_percent": 0.0,
                    "total_return_percent": 0.0,
                    "alpha_percent": 0.0,
                    "completed_trades": 0,
                    "winning_trades": 0,
                    "win_rate_percent": 0.0,
                    "wilson_win_rate_lower_bound_percent": 0.0,
                    "max_drawdown_percent": 0.0,
                    "open_position_count": 0,
                }
            )
            continue

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
                initial_capital=float(candidate.parameters.get("initial_capital", 1_000_000.0)),
                liquidate_at_end=True,
            )
            cache[cache_key] = benchmark_report

        benchmark_return = _benchmark_return(benchmark_report)
        strategy_fingerprint = metrics.get("data_fingerprint")
        benchmark_fingerprint = _validation_metrics(benchmark_report).get("data_fingerprint")
        if strategy_fingerprint:
            data_fingerprints.add(str(strategy_fingerprint))
        if benchmark_fingerprint:
            data_fingerprints.add(str(benchmark_fingerprint))
        strategy_return = float(metrics.get("total_return_percent", 0.0) or 0.0)
        completed = int(metrics.get("completed_trades", 0) or 0)
        winning = int(metrics.get("winning_trades", 0) or 0)
        rows.append(
            {
                **asdict(regime_slice),
                "market_regime": regime.value,
                "regime_as_of_date": regime_audit.get("as_of_date"),
                "regime_method": regime_audit.get("method"),
                "regime_confidence": regime_audit.get("confidence"),
                "regime_audit": regime_audit,
                "benchmark_code": benchmark_code,
                "evidence_available": True,
                "evidence_reason": None,
                "strategy_data_fingerprint": strategy_fingerprint,
                "benchmark_data_fingerprint": benchmark_fingerprint,
                "benchmark_return_percent": round(benchmark_return, 4),
                "total_return_percent": round(strategy_return, 4),
                "alpha_percent": round(strategy_return - benchmark_return, 4),
                "completed_trades": completed,
                "winning_trades": winning,
                "win_rate_percent": round(winning / completed * 100.0 if completed else 0.0, 4),
                "wilson_win_rate_lower_bound_percent": round(
                    wilson_lower_bound(winning, completed) * 100.0,
                    4,
                ),
                "max_drawdown_percent": round(abs(float(metrics.get("max_drawdown_percent", 0.0) or 0.0)), 4),
                "open_position_count": int(metrics.get("open_position_count", 0) or 0),
            }
        )

    by_regime, robustness = _aggregate_regime_rows(
        rows,
        min_completed_trades_per_regime=min_completed_trades_per_regime,
        max_drawdown_percent=max_drawdown_percent,
    )
    robustness.update(
        {
            "regime_window_extended": extension_years > 0,
            "regime_extension_years": extension_years,
            "max_regime_extension_years": max(0, int(max_extension_years)),
            "missing_regimes_after_extension": list(missing_after_extension),
            "base_train_start": split.train_start,
            "effective_regime_start": (
                labelled_slices[0][0].start_date if labelled_slices else split.train_start
            ),
            "effective_regime_end": split.validation_end,
            "adaptive_extension_is_train_feedback": False,
        }
    )
    return MarketRegimeMatrix(
        candidate_id=candidate.candidate_id,
        benchmark_code=benchmark_code,
        slices=tuple(rows),
        by_regime=by_regime,
        robustness=robustness,
        data_fingerprints=tuple(sorted(data_fingerprints)),
    )
