from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def _profile(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "loss_tolerance": 3,
        "investment_horizon": 3,
        "liquidity_need": 2,
        "investment_experience": 3,
        "income_stability": 3,
        "business_dependency": 2,
        "wealth_concentration": 2,
        "goal_priority": "income",
    }
    payload.update(overrides)
    return payload


def test_tbb_decision_is_non_executing_explainable_and_auditable() -> None:
    response = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["human_review_required"] is True
    assert data["governance"] == {
        "pii_collected": False,
        "exact_balance_collected": False,
        "prototype_persists_profile": False,
        "extra_fields_rejected": True,
        "execution_authority": False,
        "payment_authority": False,
        "final_holdout_interactive_access": False,
        "human_review_required": True,
        "fail_closed": True,
    }
    assert "自動下單" in data["blocked_capabilities"]
    assert len(data["explanations"]) == 7
    assert len(data["audit"]["decision_fingerprint"]) == 20
    assert data["audit"]["model_version"] == "bizwealth-guard-v2.1"
    assert sum(
        item["target_percent"] for item in data["allocation_envelope"]
    ) == 100


def test_capacity_and_hard_caps_override_high_risk_appetite() -> None:
    response = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(
            loss_tolerance=4,
            investment_horizon=4,
            liquidity_need=4,
            investment_experience=4,
            income_stability=1,
            business_dependency=4,
            wealth_concentration=4,
            goal_priority="growth",
        ),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["willingness_score"] == 100
    assert data["capacity_score"] == 0
    assert data["risk_code"] == "R1"
    assert data["decision_state"] == "REVIEW_REQUIRED"
    assert data["audit"]["hard_caps_applied"]
    assert any(
        item["state"] == "BLOCK" for item in data["stress_checks"]
    )
    assert data["profile_conflicts"]


def test_strong_capacity_profile_can_enter_restricted_research() -> None:
    response = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(
            loss_tolerance=4,
            investment_horizon=4,
            liquidity_need=1,
            investment_experience=4,
            income_stability=4,
            business_dependency=1,
            wealth_concentration=1,
            goal_priority="growth",
        ),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["risk_code"] == "R4"
    assert data["decision_state"] == "RESEARCH_ALLOWED"
    assert data["profile_conflicts"] == []
    assert data["audit"]["hard_caps_applied"] == []
    growth = next(
        item
        for item in data["allocation_envelope"]
        if item["name"] == "全球分散成長"
    )
    assert growth["target_percent"] == 50


def test_goal_changes_envelope_but_never_raises_risk_band() -> None:
    liquid = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(goal_priority="liquidity"),
    ).json()
    growth = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(goal_priority="growth"),
    ).json()

    assert liquid["risk_code"] == growth["risk_code"]
    assert liquid["risk_score"] == growth["risk_score"]
    assert liquid["allocation_envelope"] != growth["allocation_envelope"]


def test_decision_fingerprint_is_deterministic_without_storing_raw_profile() -> None:
    first = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(),
    ).json()
    second = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(),
    ).json()

    assert (
        first["audit"]["decision_fingerprint"]
        == second["audit"]["decision_fingerprint"]
    )
    assert first["governance"]["prototype_persists_profile"] is False


def test_hard_block_removes_satellite_research_from_allocation() -> None:
    response = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(
            loss_tolerance=4,
            investment_horizon=1,
            liquidity_need=1,
            investment_experience=4,
            income_stability=4,
            business_dependency=1,
            wealth_concentration=1,
            goal_priority="growth",
        ),
    )

    assert response.status_code == 200
    data = response.json()
    assert data["risk_code"] == "R2"
    satellite = next(
        item
        for item in data["allocation_envelope"]
        if item["name"] == "衛星策略研究"
    )
    assert satellite["target_percent"] == 0
    assert sum(
        item["target_percent"] for item in data["allocation_envelope"]
    ) == 100


def test_tbb_suitability_rejects_unknown_sensitive_or_invalid_input() -> None:
    extra = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(national_id="A123456789"),
    )
    exact_balance = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(account_balance=10_000_000),
    )
    out_of_range = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(loss_tolerance=9),
    )
    invalid_goal = client.post(
        "/api/tbb-wealth/suitability",
        json=_profile(goal_priority="guaranteed_profit"),
    )

    assert extra.status_code == 422
    assert exact_balance.status_code == 422
    assert out_of_range.status_code == 422
    assert invalid_goal.status_code == 422
