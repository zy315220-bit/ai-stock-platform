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
) -> dict[str, object]:
    """Run a bounded validation-only autonomous research session."""
    try:
        split = build_research_split(start_date, end_date)
        candidates = generate_parameter_candidates()
        session = run_autoresearch(
            stock_code,
            split,
            candidates,
            backtest_fn=backtest_stock,
            max_generations=max_generations,
            max_experiments=max_experiments,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    best = serialize_result(session.best_result) if session.best_result else None
    return {
        "stock_code": stock_code,
        "experiments_run": session.experiments_run,
        "generations_run": len(session.rounds),
        "stopped_reason": session.stopped_reason,
        "best_result": best,
        "holdout_status": "LOCKED_REQUIRES_PROMOTION_GATE",
        "split": {
            "train": [split.train_start, split.train_end],
            "validation": [split.validation_start, split.validation_end],
            "holdout": [split.holdout_start, split.holdout_end],
        },
    }
