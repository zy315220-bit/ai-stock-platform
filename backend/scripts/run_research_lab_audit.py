from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from app.services.research_lab.autoresearch import run_autoresearch
from app.services.research_lab.evolution import generate_parameter_candidates
from app.services.research_lab.models import ExperimentDecision, ResearchSplit
from app.services.research_lab.promotion import evaluate_holdout_promotion
from app.services.research_lab.runner import serialize_result
from app.services.research_lab.walk_forward import run_walk_forward

STOCK_CODE = "2330"
SPLIT = ResearchSplit("2020-01-01", "2022-12-31", "2023-01-01", "2024-12-31", "2025-01-01", "2025-12-31")
OUT = Path("research_artifacts/research_lab_2330_latest.json")


def main() -> None:
    candidates = generate_parameter_candidates(entry_scores=(55, 60, 65, 70), exit_scores=(35, 40, 45, 50))
    session = run_autoresearch(
        STOCK_CODE,
        SPLIT,
        candidates,
        max_generations=4,
        max_experiments=48,
        top_k=3,
        target_score=75.0,
    )
    best = session.best_result
    payload = {
        "schema_version": 1,
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "stock_code": STOCK_CODE,
        "split": asdict(SPLIT),
        "experiments_run": session.experiments_run,
        "stopped_reason": session.stopped_reason,
        "rounds": [
            {
                "generation": r.generation,
                "evaluated": [serialize_result(x) for x in r.evaluated],
                "survivors": [asdict(x) for x in r.survivors],
            }
            for r in session.rounds
        ],
        "best_validation": serialize_result(best) if best else None,
        "walk_forward": None,
        "promotion": None,
    }
    if best is not None:
        wf = run_walk_forward(STOCK_CODE, best.candidate)
        payload["walk_forward"] = asdict(wf)
        if best.decision is ExperimentDecision.HOLDOUT_READY:
            promotion = evaluate_holdout_promotion(STOCK_CODE, SPLIT, best)
            payload["promotion"] = asdict(promotion)
        else:
            payload["promotion"] = {
                "promoted": False,
                "reason": "best validation candidate did not reach HOLDOUT_READY; holdout intentionally not opened",
            }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    print(json.dumps({
        "artifact": str(OUT),
        "stock_code": STOCK_CODE,
        "experiments_run": session.experiments_run,
        "stopped_reason": session.stopped_reason,
        "best_score": best.research_score if best else None,
        "best_decision": best.decision.value if best else None,
        "promotion": payload["promotion"],
    }, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
