from app.services.market_context import (
    _valuation_score,
    get_fundamental_snapshot,
    score_news_titles,
)
from app.services.scanner_service import _scanner_score


def test_valuation_score_rewards_lower_valuation_and_yield() -> None:
    attractive = _valuation_score(12.0, 1.2, 5.5)
    expensive = _valuation_score(55.0, 9.0, 0.5)

    assert attractive > expensive
    assert 0 <= attractive <= 100
    assert 0 <= expensive <= 100


def test_etf_does_not_use_company_valuation() -> None:
    snapshot = get_fundamental_snapshot("0056", "上市")

    assert snapshot["available"] is False
    assert snapshot["score"] is None
    assert "ETF" in snapshot["label"]


def test_news_score_uses_transparent_keyword_hits() -> None:
    positive_score, positive_hits, negative_hits = score_news_titles(
        ["公司營收成長並創高", "接單優於預期"]
    )
    negative_score, _, negative_count = score_news_titles(
        ["公司轉虧並下修展望", "營收衰退"]
    )

    assert positive_hits > negative_hits
    assert negative_count > 0
    assert positive_score > negative_score


def test_scanner_score_rewards_price_strength_without_being_ai_score() -> None:
    strong, reasons = _scanner_score(
        change_percent=3.0,
        open_price=100,
        high_price=105,
        low_price=99,
        current_price=104.5,
        total_volume=10_000_000,
    )
    weak, _ = _scanner_score(
        change_percent=-2.0,
        open_price=100,
        high_price=101,
        low_price=96,
        current_price=96.5,
        total_volume=20_000,
    )

    assert strong > weak
    assert reasons
