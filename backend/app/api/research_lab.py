from __future__ import annotations

from datetime import date
from fastapi import APIRouter, HTTPException, Query
from app.services.research_lab.autoresearch import run_autoresearch
from app.services.research_lab.evolution import generate_parameter_candidates
from app.services.research_lab.runner import serialize_result
from app.services.research_lab.splits import build_research_split
from app.services.backtest.engine import backtest_stock

router = APIRouter()


@router.post("/run")
def run_research(
    stock_code: str = Query(..., min_length=4, max_length=10),
    start_date: date = Query(...),
    end_date: date = Query(...),
    max_generations: int = Query(3, ge=1, le=10),
    max_experiments: int = Query(40, ge=1, le=200),
    min_validation_trades: int = Query(8, ge=1, le=100),
) -> dict[str, object]:
    """Run bounded validation-only autonomous research and return an auditable generation trail."""
    try:
        split = build_research_split(start_date, end_date)
        session = run_autoresearch(
            stock_code,
            split,
            generate_parameter_candidates(),
            backtest_fn=backtest_stock,
            max_generations=max_generations,
            max_experiments=max_experiments,
            min_validation_trades=min_validation_trades,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    rounds = []
    for round_ in session.rounds:
        rounds.append({
            "generation": round_.generation,
            "evaluated_count": len(round_.evaluated),
            "survivor_count": len(round_.survivors),
            "evaluated": [serialize_result(result) for result in round_.evaluated],
            "survivors": [
                {"candidate_id": c.candidate_id, "parent_id": c.parent_id, "strategy_family": c.strategy_family, "parameters": c.parameters, "hypothesis": c.hypothesis}
                for c in round_.survivors
            ],
        })

    return {
        "stock_code": stock_code,
        "experiments_run": session.experiments_run,
        "generations_run": len(session.rounds),
        "stopped_reason": session.stopped_reason,
        "best_result": serialize_result(session.best_result) if session.best_result else None,
        "rounds": rounds,
        "research_audit": {
            "candidate_generation": "deterministic_grid_then_local_mutation",
            "selection": "research_score_ranked_non_discarded_top_k",
            "holdout_used_during_search": False,
            "validation_policy": {"min_completed_trades": min_validation_trades},
            "bounded_by": {"max_generations": max_generations, "max_experiments": max_experiments},
        },
        "holdout_status": "LOCKED_REQUIRES_PROMOTION_GATE",
        "split": {"train": [split.train_start, split.train_end], "validation": [split.validation_start, split.validation_end], "holdout": [split.holdout_start, split.holdout_end]},
    }
