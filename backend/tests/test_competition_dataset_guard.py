import pandas as pd

from app.services.competition_dataset_guard import (
    competition_dataset_manifest,
    prepare_competition_frame,
)


def frame(*, close: float = 10.5, dividend: float = 0.5) -> pd.DataFrame:
    result = pd.DataFrame(
        {
            "Open": [10.0, close],
            "High": [10.2, close + 0.2],
            "Low": [9.8, close - 0.2],
            "Close": [10.0, close],
            "Volume": [1_000.0, 1_100.0],
        },
        index=pd.to_datetime(["2026-01-02", "2026-01-05"]),
    )
    result.attrs.update(
        {
            "stock_code": "0050",
            "source": "official-test",
            "price_basis": "latest-unit split-adjusted",
            "corporate_action_validated": True,
            "split_adjustments": [],
            "dividends": [
                {
                    "ex_date": "2026-01-05",
                    "amount": dividend,
                    "source": "official-test",
                }
            ],
            "dividend_source": "official-test",
        }
    )
    return result


def manifest(item: pd.DataFrame) -> dict:
    prepared = prepare_competition_frame(item, "0050")
    return competition_dataset_manifest({"0050": prepared})


def test_identical_dataset_keeps_same_fingerprint() -> None:
    first = manifest(frame())
    second = manifest(frame())
    assert first["fingerprint"] == second["fingerprint"]
    assert first["symbols"]["0050"]["research_dataset_version"] == second[
        "symbols"
    ]["0050"]["research_dataset_version"]


def test_dividend_correction_invalidates_ranking_dataset() -> None:
    before = manifest(frame(dividend=0.5))
    after = manifest(frame(dividend=0.6))
    assert before["fingerprint"] != after["fingerprint"]


def test_ohlcv_correction_invalidates_ranking_dataset() -> None:
    before = manifest(frame(close=10.5))
    after = manifest(frame(close=10.6))
    assert before["fingerprint"] != after["fingerprint"]


def test_manifest_retains_auditable_price_digest() -> None:
    item = manifest(frame())["symbols"]["0050"]["research_dataset_manifest"]
    assert item["schema_version"] == "research-dataset-v2"
    assert item["start"] == "2026-01-02"
    assert item["end"] == "2026-01-05"
    assert item["row_count"] == 2
    assert len(item["ohlcv_sha256"]) == 64
