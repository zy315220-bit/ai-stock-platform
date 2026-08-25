from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.services.research_lab.competition_bridge import (
    build_competition_challenger_roster,
)
from scripts.run_daily_autoresearch import write_json_atomic


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build competition challenger queue from certified Final Holdout robots"
    )
    parser.add_argument("--certified-registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    registry = json.loads(args.certified_registry.read_text(encoding="utf-8"))
    roster = build_competition_challenger_roster(registry)
    write_json_atomic(args.output, roster)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "status": roster["status"],
                "challenger_count": roster["challenger_count"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
