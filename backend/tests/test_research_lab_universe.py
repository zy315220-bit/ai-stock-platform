from __future__ import annotations

from pathlib import Path

from app.services.research_universe import (
    CORE_RESEARCH_UNIVERSE,
    DAILY_RESEARCH_UNIVERSE,
    RESEARCH_EXPANSION_UNIVERSE,
)
from app.services.scanner_service import SCANNER_UNIVERSE


def test_research_universe_is_exactly_40_unique_symbols() -> None:
    assert len(DAILY_RESEARCH_UNIVERSE) == 40
    assert len(set(DAILY_RESEARCH_UNIVERSE)) == 40
    assert len(CORE_RESEARCH_UNIVERSE) == 20
    assert len(RESEARCH_EXPANSION_UNIVERSE) == 20


def test_existing_20_symbol_memory_universe_is_preserved() -> None:
    assert CORE_RESEARCH_UNIVERSE == SCANNER_UNIVERSE
    assert DAILY_RESEARCH_UNIVERSE[:20] == SCANNER_UNIVERSE


def test_public_scanner_is_not_expanded_with_autonomous_research() -> None:
    assert len(SCANNER_UNIVERSE) == 20
    assert set(RESEARCH_EXPANSION_UNIVERSE).isdisjoint(SCANNER_UNIVERSE)


def test_daily_workflow_keeps_schedule_and_matches_40_symbol_universe() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    workflow = (repo_root / ".github/workflows/daily-autoresearch.yml").read_text(
        encoding="utf-8"
    )
    assert 'cron: "30 22,10 * * *"' in workflow
    assert "max-parallel: 4" in workflow
    for symbol in DAILY_RESEARCH_UNIVERSE:
        assert f'- "{symbol}"' in workflow
