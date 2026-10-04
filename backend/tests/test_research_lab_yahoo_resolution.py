from unittest.mock import Mock

import stock


def _response(granularity):
    response = Mock()
    response.json.return_value = {"chart": {"result": [{
        "meta": {"dataGranularity": granularity},
        "timestamp": [1717376400, 1717462800],
        "indicators": {"quote": [{
            "open": [100, 101], "high": [102, 103], "low": [99, 100],
            "close": [101, 102], "volume": [1000, 1100],
        }]},
    }]}}
    return response


def test_maximum_daily_history_uses_explicit_dates(monkeypatch):
    request = Mock(return_value=_response("1d"))
    monkeypatch.setattr(stock.requests, "get", request)

    frame = stock._download_yahoo_chart("0050.TW", "max", "1d")

    assert len(frame) == 2
    params = request.call_args.kwargs["params"]
    assert "range" not in params
    assert params["period1"] == 0
    assert params["period2"] > params["period1"]
    assert params["interval"] == "1d"


def test_monthly_response_is_never_accepted_as_daily_history(monkeypatch):
    monkeypatch.setattr(stock.requests, "get", Mock(return_value=_response("1mo")))
    assert stock._download_yahoo_chart("0050.TW", "max", "1d").empty


def test_wrong_resolution_falls_back_to_the_daily_transport(monkeypatch):
    request = Mock(return_value=_response("1mo"))
    monkeypatch.setattr(stock.requests, "get", request)
    daily = stock.pd.DataFrame({"Close": [101.0]})
    alternate = Mock(return_value=daily)
    monkeypatch.setattr(stock.yf, "download", alternate)

    frame = stock._download_yfinance("0050.TW", "max", "1d")

    assert not frame.empty
    alternate.assert_called_once()
    assert alternate.call_args.kwargs["interval"] == "1d"
