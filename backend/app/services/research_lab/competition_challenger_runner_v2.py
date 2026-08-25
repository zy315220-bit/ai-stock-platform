from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from app.services.competition_runner import (
    COMMISSION_RATE,
    COMPETITION_UNIVERSE,
    DEFAULT_INITIAL_CAPITAL,
    ETF_TRANSACTION_TAX_RATE,
    MIN_FORWARD_TRADES_FOR_CHAMPION,
    ROBOT_SPECS,
    _aggregate_portfolio,
    _date_text,
    _download_competition_frames,
    _simulate_symbol,
)
from app.services.competition_service import freeze_robot_spec, rank_robot_results
from score_engine.calculate import calculate_score

from .competition_bridge import CHALLENGER_SCHEMA_VERSION, QUEUE_STATUS
from .competition_challenger_runner import (
    COST_MODEL_ID,
    MARKET_UNIVERSE_ID,
    RISK_MODEL_ID,
    build_causal_score_series,
    simulate_challenger_symbol,
)


TOURNAMENT_SCHEMA_VERSION = 2


def _waiting(reason: str, challenger_count: int = 0) -> dict[str, Any]:
    return {
        "schema_version": TOURNAMENT_SCHEMA_VERSION,
        "status": "ACCUMULATING_POST_CERTIFICATION_EVIDENCE",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "challenger_count": challenger_count,
        "promotion": {
            "challenger_replaced_incumbent": False,
            "promoted_robot_id": None,
            "reason": reason,
            "competition_feedback_to_same_campaign_train": False,
        },
    }


def _ranking_row(
    *,
    robot_id: str,
    version: str,
    fingerprint: str,
    capital: float,
    start: pd.Timestamp,
    end: pd.Timestamp,
    forward: dict[str, Any],
) -> dict[str, Any]:
    return {
        "robot_id": robot_id,
        "robot_version": version,
        "rule_fingerprint": fingerprint,
        "initial_capital": capital,
        "period_start": _date_text(start),
        "period_end": _date_text(end),
        "cost_model_id": COST_MODEL_ID,
        "risk_model_id": RISK_MODEL_ID,
        "market_universe_id": MARKET_UNIVERSE_ID,
        "trade_count": forward["trade_count"],
        "winning_trade_count": forward["winning_trade_count"],
        "total_return_percent": forward["total_return_percent"],
        "max_drawdown_percent": forward["max_drawdown_percent"],
    }


def run_challenger_tournament_on_frames_v2(
    frames: dict[str, pd.DataFrame],
    challenger_roster: dict[str, Any],
    *,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
    score_fn=calculate_score,
) -> dict[str, Any]:
    if challenger_roster.get("schema_version") != CHALLENGER_SCHEMA_VERSION:
        raise ValueError("Unsupported challenger roster schema")
    challengers = challenger_roster.get("challengers")
    if not isinstance(challengers, list):
        raise ValueError("Challenger roster must contain a list")
    if int(challenger_roster.get("challenger_count", -1)) != len(challengers):
        raise ValueError("Challenger roster count mismatch")
    if not challengers:
        return {
            "schema_version": TOURNAMENT_SCHEMA_VERSION,
            "status": "WAITING_FOR_CERTIFIED_ROBOT",
            "executed_at": datetime.now(timezone.utc).isoformat(),
            "challenger_count": 0,
            "promotion": {
                "challenger_replaced_incumbent": False,
                "promoted_robot_id": None,
                "reason": "No Final-Holdout-certified challenger exists yet.",
                "competition_feedback_to_same_campaign_train": False,
            },
        }
    if any(challenger.get("status") != QUEUE_STATUS for challenger in challengers):
        raise ValueError("Only queued certified challengers may compete")
    missing = [code for code in COMPETITION_UNIVERSE if code not in frames]
    if missing:
        raise ValueError("Competition frames missing: " + ",".join(missing))

    not_before_values: list[pd.Timestamp] = []
    for challenger in challengers:
        contract = challenger.get("challenge_contract") or {}
        if contract.get("post_certification_evidence_only") is not True:
            raise ValueError("Challenger lacks post-certification evidence contract")
        value = contract.get("challenge_not_before")
        if not value:
            raise ValueError("Challenger lacks challenge_not_before")
        not_before_values.append(pd.Timestamp(str(value)).normalize())

    common_start = max(not_before_values)
    latest_date = min(pd.Timestamp(frames[code].index.max()).normalize() for code in COMPETITION_UNIVERSE)
    if latest_date < common_start:
        return {
            **_waiting(
                "Certified challengers are quarantined until fresh market data exists after certification.",
                len(challengers),
            ),
            "common_fresh_window": {
                "start": _date_text(common_start),
                "end": _date_text(latest_date),
                "available": False,
            },
        }

    capital = float(initial_capital)
    per_symbol_capital = capital / len(COMPETITION_UNIVERSE)
    ranking_rows: list[dict[str, Any]] = []
    incumbent_outputs: list[dict[str, Any]] = []

    for spec in ROBOT_SPECS:
        robot_id = str(spec["robot_id"])
        symbol_results = [
            _simulate_symbol(
                frame=frames[code],
                stock_code=code,
                robot_id=robot_id,
                segment="post_certification",
                start=common_start,
                end=latest_date,
                initial_capital=per_symbol_capital,
                commission_rate=COMMISSION_RATE,
                transaction_tax_rate=ETF_TRANSACTION_TAX_RATE,
            )
            for code in COMPETITION_UNIVERSE
        ]
        forward = _aggregate_portfolio(symbol_results, initial_capital=capital)
        frozen = freeze_robot_spec(spec)
        ranking_rows.append(
            _ranking_row(
                robot_id=robot_id,
                version="1",
                fingerprint=frozen["rule_fingerprint"],
                capital=capital,
                start=common_start,
                end=latest_date,
                forward=forward,
            )
        )
        incumbent_outputs.append(
            {
                "origin": "incumbent_competition",
                "robot_id": robot_id,
                "name": spec.get("name"),
                "family": spec.get("family"),
                "rule_fingerprint": frozen["rule_fingerprint"],
                "forward": forward,
            }
        )

    score_series_by_symbol = {
        code: build_causal_score_series(frames[code], score_fn=score_fn)
        for code in COMPETITION_UNIVERSE
    }
    challenger_outputs: list[dict[str, Any]] = []
    for challenger in challengers:
        symbol_results = [
            simulate_challenger_symbol(
                frame=frames[code],
                score_series=score_series_by_symbol[code],
                stock_code=code,
                challenger=challenger,
                start=common_start,
                end=latest_date,
                initial_capital=per_symbol_capital,
            )
            for code in COMPETITION_UNIVERSE
        ]
        forward = _aggregate_portfolio(symbol_results, initial_capital=capital)
        robot_id = str(challenger["robot_id"])
        spec = challenger.get("spec") or {}
        ranking_rows.append(
            _ranking_row(
                robot_id=robot_id,
                version=str(challenger.get("challenger_id") or "1"),
                fingerprint=str(challenger["rule_fingerprint"]),
                capital=capital,
                start=common_start,
                end=latest_date,
                forward=forward,
            )
        )
        challenger_outputs.append(
            {
                "origin": "research_lab_certified",
                "robot_id": robot_id,
                "name": spec.get("name"),
                "family": spec.get("family"),
                "challenger_id": challenger.get("challenger_id"),
                "rule_fingerprint": challenger.get("rule_fingerprint"),
                "challenge_contract": challenger.get("challenge_contract") or {},
                "research_provenance": challenger.get("research_provenance") or {},
                "forward": forward,
            }
        )

    ranking = rank_robot_results(ranking_rows)
    rank_by_id = {row["robot_id"]: row for row in ranking["robots"]}
    for output in incumbent_outputs + challenger_outputs:
        row = rank_by_id[output["robot_id"]]
        output["rank"] = row["rank"]
        output["wilson_lower_percent"] = row["wilson_lower_percent"]
        output["wilson_upper_percent"] = row["wilson_upper_percent"]
    incumbent_outputs.sort(key=lambda item: int(item["rank"]))
    challenger_outputs.sort(key=lambda item: int(item["rank"]))

    overall_leader = ranking["robots"][0]
    challenger_ids = {row["robot_id"] for row in challenger_outputs}
    challenger_won = overall_leader["robot_id"] in challenger_ids
    qualified = int(overall_leader["trade_count"]) >= MIN_FORWARD_TRADES_FOR_CHAMPION
    replaced = challenger_won and qualified

    incumbent_leader = incumbent_outputs[0]
    return {
        "schema_version": TOURNAMENT_SCHEMA_VERSION,
        "status": "completed",
        "executed_at": datetime.now(timezone.utc).isoformat(),
        "challenger_count": len(challenger_outputs),
        "evaluation_policy": {
            "post_certification_evidence_only": True,
            "final_holdout_overlap_forbidden": True,
            "common_fresh_comparison_window": True,
            "same_capital_cost_risk_universe": True,
            "competition_feedback_to_same_campaign_train": False,
        },
        "common_fresh_window": {
            "start": _date_text(common_start),
            "end": _date_text(latest_date),
            "available": True,
        },
        "ranking": {
            "primary_metric": "post-certification Wilson 95% win-rate lower bound",
            "minimum_forward_trades_for_champion": MIN_FORWARD_TRADES_FOR_CHAMPION,
            "all_robot_count": len(ranking["robots"]),
            "robots": ranking["robots"],
        },
        "incumbent_leader": {
            "robot_id": incumbent_leader["robot_id"],
            "name": incumbent_leader.get("name"),
            "rank": incumbent_leader["rank"],
        },
        "overall_leader": {
            "robot_id": overall_leader["robot_id"],
            "rank": overall_leader["rank"],
            "trade_count": int(overall_leader["trade_count"]),
            "wilson_lower_percent": overall_leader["wilson_lower_percent"],
            "qualified": qualified,
            "origin": "research_lab_certified" if challenger_won else "incumbent_competition",
        },
        "promotion": {
            "challenger_replaced_incumbent": replaced,
            "promoted_robot_id": overall_leader["robot_id"] if replaced else None,
            "defeated_incumbent_robot_id": incumbent_leader["robot_id"] if replaced else None,
            "reason": (
                "Certified challenger won on fresh post-certification evidence and met the minimum trade gate."
                if replaced
                else (
                    "Certified challenger leads, but has not accumulated enough fresh post-certification trades."
                    if challenger_won
                    else "Incumbent retained the title on the common fresh post-certification window."
                )
            ),
            "competition_feedback_to_same_campaign_train": False,
        },
        "challengers": challenger_outputs,
        "incumbents": incumbent_outputs,
    }


def run_certified_challenger_tournament_v2(
    challenger_roster: dict[str, Any],
    *,
    initial_capital: float = DEFAULT_INITIAL_CAPITAL,
) -> dict[str, Any]:
    challengers = challenger_roster.get("challengers") or []
    if not challengers:
        return run_challenger_tournament_on_frames_v2(
            {}, challenger_roster, initial_capital=initial_capital
        )
    frames, _, _ = _download_competition_frames()
    return run_challenger_tournament_on_frames_v2(
        frames,
        challenger_roster,
        initial_capital=initial_capital,
    )
