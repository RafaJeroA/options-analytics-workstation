import pytest

from app.quant.payoff import EXACT_PAYOFF_UNAVAILABLE_REASON
from app.services.adapters.base import AdapterUnavailableError, UnknownContractError
from app.services.market_service import get_market_service


def test_health_route(client) -> None:
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["data_mode"] == "mock"


def test_underlying_search_route(client) -> None:
    response = client.get("/underlyings/search", params={"q": "SPY"})
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["symbol"] == "SPY"


def test_chain_route_returns_calls_and_puts(client) -> None:
    response = client.get("/underlyings/SPY/chains")
    assert response.status_code == 200
    payload = response.json()
    assert payload["symbol"] == "SPY"
    assert len(payload["calls"]) > 0
    assert len(payload["puts"]) > 0


def test_strategy_price_route_accepts_explicit_underlying_price_assumption(client) -> None:
    chain_response = client.get("/underlyings/SPY/chains")
    assert chain_response.status_code == 200
    chain = chain_response.json()
    call = chain["calls"][0]

    response = client.post(
        "/strategies/price",
        json={
            "strategy": {
                "name": "Long Call",
                "underlying_symbol": "SPY",
                "underlying_price": chain["underlying"]["spot"],
                "legs": [
                    {
                        "leg_id": "leg-1",
                        "instrument_type": "option",
                        "side": "long",
                        "quantity": 1,
                        "contract": call["contract"],
                        "quote": call,
                        "entry_price": call["mark"],
                    }
                ],
            },
            "assumptions": {
                "underlying_price": chain["underlying"]["spot"],
                "risk_free_rate": 0.03,
                "dividend_yield": 0.01,
                "days_forward": 5,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["assumptions"]["underlying_price"] == chain["underlying"]["spot"]
    assert payload["underlying_symbol"] == "SPY"


def _mixed_strategy_payload(client) -> dict[str, object]:
    chain_response = client.get("/underlyings/SPY/chains")
    assert chain_response.status_code == 200
    first_chain = chain_response.json()
    second_expiration = first_chain["expirations"][1]
    second_response = client.get("/underlyings/SPY/chains", params={"expiration": second_expiration})
    assert second_response.status_code == 200
    second_chain = second_response.json()
    first_call = next(
        call
        for call in first_chain["calls"]
        if call["mark"] is not None and call["mark"] > 0 and call["implied_vol"] is not None
    )
    second_call = next(
        call
        for call in second_chain["calls"]
        if call["contract"]["strike"] == first_call["contract"]["strike"]
        and call["mark"] is not None
        and call["mark"] > 0
        and call["implied_vol"] is not None
    )
    spot = first_chain["underlying"]["spot"]
    return {
        "name": "Mixed Call Calendar",
        "underlying_symbol": "SPY",
        "underlying_price": spot,
        "legs": [
            {
                "leg_id": "near",
                "instrument_type": "option",
                "side": "short",
                "quantity": 1,
                "contract": first_call["contract"],
                "quote": first_call,
                "entry_price": first_call["mark"],
            },
            {
                "leg_id": "far",
                "instrument_type": "option",
                "side": "long",
                "quantity": 1,
                "contract": second_call["contract"],
                "quote": second_call,
                "entry_price": second_call["mark"],
            },
        ],
    }


def test_strategy_price_route_returns_unavailable_exact_metrics_for_mixed_expirations(client) -> None:
    strategy = _mixed_strategy_payload(client)
    response = client.post(
        "/strategies/price",
        json={
            "strategy": strategy,
            "assumptions": {
                "valuation_date": "2026-07-31",
                "underlying_price": strategy["underlying_price"],
                "risk_free_rate": 0.03,
                "dividend_yield": 0.01,
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["entry_cost"] is not None
    assert payload["current_value"] is not None
    assert payload["theoretical_value"] is not None
    assert payload["pnl_open"] is not None
    assert payload["max_profit"] is None
    assert payload["max_loss"] is None
    assert payload["max_profit_state"] == "unavailable"
    assert payload["max_loss_state"] == "unavailable"
    assert payload["breakevens"] == []
    assert payload["breakeven_intervals"] == []
    assert payload["payoff"] == []
    assert payload["payoff_unavailable_reason"] == EXACT_PAYOFF_UNAVAILABLE_REASON
    assert payload["pricing_state"] == "partial"
    assert EXACT_PAYOFF_UNAVAILABLE_REASON in payload["warnings"]


def test_mixed_expiration_scenario_route_keeps_conditional_values_and_serialization(client) -> None:
    strategy = _mixed_strategy_payload(client)
    response = client.post(
        "/strategies/scenario-grid",
        json={
            "strategy": strategy,
            "scenario": {
                "valuation_date": "2026-07-31",
                "underlying_moves_pct": [0.0],
                "implied_vol_shifts": [0.0],
                "days_forward": [0, 7, 30],
                "risk_free_rate": 0.03,
                "dividend_yield": 0.01,
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["conditional_settlement"] is True
    assert len(payload["points"]) == 3
    assert all(point["theoretical_value"] is not None for point in payload["points"])
    states = {state["days_forward"]: state for state in payload["day_states"]}
    assert states[0]["expiration_state"] == "pre_expiry"
    assert states[7]["expiration_state"] == "mixed"
    assert states[30]["expiration_state"] == "at_or_after_expiry"
    assert "conditional settlement illustration" in states[7]["message"]
    assert "not a global risk bound" in states[30]["message"]


def test_mixed_expiration_missing_entry_keeps_model_and_input_explanations(client) -> None:
    strategy = _mixed_strategy_payload(client)
    strategy["legs"][1]["entry_price"] = None
    response = client.post(
        "/strategies/price",
        json={
            "strategy": strategy,
            "assumptions": {
                "valuation_date": "2026-07-31",
                "underlying_price": strategy["underlying_price"],
                "risk_free_rate": 0.03,
                "dividend_yield": 0.01,
            },
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["pricing_state"] == "partial"
    assert (
        payload["status_message"]
        == "Strategy pricing incomplete: one or more legs have no usable entry premium."
    )
    assert payload["payoff_unavailable_reason"] == EXACT_PAYOFF_UNAVAILABLE_REASON
    assert any("settlement spots can differ" in warning for warning in payload["warnings"])
    assert any("Entry premium is unavailable" in warning for warning in payload["warnings"])


def test_strategy_price_route_returns_controlled_result_for_unpriced_strategy(client) -> None:
    chain_response = client.get("/underlyings/SPY/chains")
    assert chain_response.status_code == 200
    chain = chain_response.json()
    call = chain["calls"][0]

    response = client.post(
        "/strategies/price",
        json={
            "strategy": {
                "name": "Unpriced Long Call",
                "underlying_symbol": "SPY",
                "underlying_price": chain["underlying"]["spot"],
                "legs": [
                    {
                        "leg_id": "leg-1",
                        "instrument_type": "option",
                        "side": "long",
                        "quantity": 1,
                        "contract": call["contract"],
                        "quote": None,
                        "entry_price": None,
                    }
                ],
            },
            "assumptions": {
                "valuation_date": "2026-07-31",
                "underlying_price": chain["underlying"]["spot"],
                "risk_free_rate": 0.03,
                "dividend_yield": 0.01,
            },
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["pricing_state"] == "unavailable"
    assert payload["payoff"] == []
    assert payload["max_profit"] is None
    assert payload["max_loss"] is None
    assert (
        payload["status_message"]
        == "Strategy pricing incomplete: one or more legs have no usable implied volatility."
    )


@pytest.mark.parametrize(
    ("strategy_update", "assumptions_update", "message"),
    [
        ({"underlying_price": -1}, {}, "greater than 0"),
        (
            {"legs": [{"leg_id": "missing", "instrument_type": "option", "side": "long", "quantity": 1}]},
            {},
            "option legs require a contract",
        ),
        (
            {
                "legs": [
                    {
                        "leg_id": "wrong-symbol",
                        "instrument_type": "option",
                        "side": "long",
                        "quantity": 1,
                        "contract": {
                            "contract_id": "AAPL-2026-12-18-100.00-C",
                            "symbol": "AAPL",
                            "expiration": "2026-12-18",
                            "strike": 100,
                            "right": "call",
                        },
                    }
                ]
            },
            {},
            "does not match strategy symbol",
        ),
        ({}, {"days_forward": -1}, "greater than or equal to 0"),
    ],
)
def test_strategy_price_route_returns_actionable_422(
    client,
    strategy_update: dict[str, object],
    assumptions_update: dict[str, object],
    message: str,
) -> None:
    strategy = {"name": "Validation", "underlying_symbol": "SPY", "underlying_price": 500, "legs": []}
    strategy.update(strategy_update)
    assumptions = {"underlying_price": 500, "risk_free_rate": -0.01, "days_forward": 0}
    assumptions.update(assumptions_update)

    response = client.post("/strategies/price", json={"strategy": strategy, "assumptions": assumptions})

    assert response.status_code == 422
    assert message in response.text


def test_strategy_scenario_route_rejects_impossible_spot_and_negative_days(client) -> None:
    response = client.post(
        "/strategies/scenario-grid",
        json={
            "strategy": {
                "name": "Validation",
                "underlying_symbol": "SPY",
                "underlying_price": 500,
                "legs": [],
            },
            "scenario": {"underlying_moves_pct": [-1.0], "implied_vol_shifts": [0], "days_forward": [-1]},
        },
    )

    assert response.status_code == 422
    assert "greater than -1" in response.text
    assert "greater than or equal to 0" in response.text


def test_strategy_price_route_rejects_non_finite_json_number(client) -> None:
    response = client.post(
        "/strategies/price",
        content=(
            '{"strategy":{"name":"Validation","underlying_symbol":"SPY",'
            '"underlying_price":500,"legs":[]},"assumptions":{"underlying_price":NaN}}'
        ),
        headers={"Content-Type": "application/json"},
    )

    assert response.status_code == 422
    assert "finite number" in response.text


def test_strategy_price_route_rejects_unknown_assumption_fields(client) -> None:
    response = client.post(
        "/strategies/price",
        json={
            "strategy": {
                "name": "Validation",
                "underlying_symbol": "SPY",
                "underlying_price": 500,
                "legs": [],
            },
            "assumptions": {"underlying_price": 500, "unsupported": 1},
        },
    )

    assert response.status_code == 422
    assert "Extra inputs are not permitted" in response.text


def test_option_quote_route_maps_unknown_contract_to_404(client, monkeypatch) -> None:
    service = get_market_service()

    def stub_get_option_quote(contract_id: str):
        raise UnknownContractError(f"Requested expiration 2026-01-16 is not available for {contract_id}.")

    monkeypatch.setattr(service, "get_option_quote", stub_get_option_quote)

    response = client.get("/options/SPY-2026-01-16-530.00-C/quote")

    assert response.status_code == 404
    assert "Requested expiration 2026-01-16 is not available" in response.json()["detail"]


def test_skew_route_falls_back_when_requested_expiration_is_stale(client, monkeypatch) -> None:
    service = get_market_service()
    original_get_option_chain = service.adapter.get_option_chain

    def stub_get_option_chain(symbol: str, expiration: str | None = None):
        if expiration == "2026-01-16":
            raise AdapterUnavailableError("Requested expiration 2026-01-16 is not available.")
        return original_get_option_chain(symbol, expiration)

    monkeypatch.setattr(service.adapter, "get_option_chain", stub_get_option_chain)

    response = client.get(
        "/volatility/skew",
        params={"symbol": "SPY", "expiration": "2026-01-16"},
    )

    assert response.status_code == 200
    payload = response.json()
    assert len(payload) > 0
    assert all(point["expiration"] == payload[0]["expiration"] for point in payload)


def test_skew_route_maps_unavailable_requested_expiration_to_404(client, monkeypatch) -> None:
    service = get_market_service()

    def stub_get_volatility_skew(symbol: str, expiration: str | None = None):
        raise UnknownContractError("Requested expiration 2026-03-30 is not available.")

    monkeypatch.setattr(service, "get_volatility_skew", stub_get_volatility_skew)

    response = client.get(
        "/volatility/skew",
        params={"symbol": "SPY", "expiration": "2026-03-30"},
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "Requested expiration 2026-03-30 is not available."


def test_term_structure_route_maps_adapter_unavailability_to_503(client, monkeypatch) -> None:
    service = get_market_service()

    def stub_get_term_structure(symbol: str):
        raise AdapterUnavailableError("No usable option chain is available for SPCE.")

    monkeypatch.setattr(service, "get_term_structure", stub_get_term_structure)

    response = client.get(
        "/volatility/term-structure",
        params={"symbol": "SPCE"},
    )

    assert response.status_code == 503
    assert response.json()["detail"] == "No usable option chain is available for SPCE."


def test_watchlist_route_persists_item(client) -> None:
    create_response = client.post("/watchlist", json={"symbol": "AAPL"})
    assert create_response.status_code == 200

    list_response = client.get("/watchlist")
    assert list_response.status_code == 200
    payload = list_response.json()
    assert payload[0]["symbol"] == "AAPL"


def test_workspace_routes_persist_settings_strategy_and_recent_chain(client) -> None:
    settings_response = client.put(
        "/workspace/settings",
        json={
            "settings": {
                "theme": "dark",
                "default_rate": 0.031,
                "default_dividend_yield": 0.012,
                "watchlist_symbols": ["SPY", "QQQ"],
                "recent_symbols": ["SPY"],
                "selected_symbol": "SPY",
                "left_panel_size": 20,
                "right_panel_size": 26,
            }
        },
    )
    assert settings_response.status_code == 200
    assert settings_response.json()["default_rate"] == 0.031

    strategy_response = client.post(
        "/workspace/strategies",
        json={
            "name": "Test Vertical",
            "strategy": {
                "name": "Test Vertical",
                "underlying_symbol": "SPY",
                "underlying_price": 531.42,
                "legs": [
                    {
                        "leg_id": "leg-1",
                        "instrument_type": "stock",
                        "side": "long",
                        "quantity": 1,
                        "stock_price": 531.42,
                        "entry_price": 531.42,
                        "underlying_symbol": "SPY",
                    }
                ],
            },
        },
    )
    assert strategy_response.status_code == 200
    strategy_id = strategy_response.json()["strategy_id"]

    saved_response = client.get("/workspace/strategies")
    assert saved_response.status_code == 200
    assert saved_response.json()[0]["strategy_id"] == strategy_id

    chain_response = client.get("/underlyings/SPY/chains")
    assert chain_response.status_code == 200

    recent_response = client.get("/workspace/recent-chains")
    assert recent_response.status_code == 200
    assert recent_response.json()[0]["symbol"] == "SPY"

    delete_response = client.delete(f"/workspace/strategies/{strategy_id}")
    assert delete_response.status_code == 200
    assert delete_response.json() == {"deleted": True}
