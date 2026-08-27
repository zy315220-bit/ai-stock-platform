from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_tbb_suitability_is_non_executing_and_fail_closed() -> None:
    response = client.post(
        "/api/tbb-wealth/suitability",
        json={
            "loss_tolerance": 2,
            "investment_horizon": 3,
            "liquidity_need": 2,
            "investment_experience": 2,
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["human_review_required"] is True
    assert data["governance"]["pii_collected"] is False
    assert data["governance"]["execution_authority"] is False
    assert data["governance"]["final_holdout_interactive_access"] is False
    assert data["governance"]["fail_closed"] is True
    assert "自動下單" in data["blocked_capabilities"]


def test_tbb_suitability_rejects_unknown_or_out_of_range_input() -> None:
    extra = client.post(
        "/api/tbb-wealth/suitability",
        json={
            "loss_tolerance": 2,
            "investment_horizon": 3,
            "liquidity_need": 2,
            "investment_experience": 2,
            "national_id": "A123456789",
        },
    )
    assert extra.status_code == 422

    out_of_range = client.post(
        "/api/tbb-wealth/suitability",
        json={
            "loss_tolerance": 9,
            "investment_horizon": 3,
            "liquidity_need": 2,
            "investment_experience": 2,
        },
    )
    assert out_of_range.status_code == 422
