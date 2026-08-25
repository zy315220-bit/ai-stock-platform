from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.research_lab.competition_challenger_runner_v2 import (
    run_certified_challenger_tournament_v2,
)
from scripts.run_daily_autoresearch import write_json_atomic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Run Final-Holdout-certified challengers against incumbents using only "
            "a common post-certification evidence window"
        )
    )
    parser.add_argument("--challenger-roster", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--initial-capital", type=float, default=100000.0)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    roster = json.loads(args.challenger_roster.read_text(encoding="utf-8"))
    result = run_certified_challenger_tournament_v2(
        roster,
        initial_capital=args.initial_capital,
    )
    write_json_atomic(args.output, result)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": result.get("status"),
                "challenger_count": result.get("challenger_count"),
                "common_fresh_window": result.get("common_fresh_window"),
                "promotion": result.get("promotion"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
