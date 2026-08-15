from __future__ import annotations


def test_complete_deterministic_mock_research_workflow(client) -> None:
    search = client.get("/underlyings/search", params={"q": "SPY"})
    assert search.status_code == 200
    assert search.json()[0]["market_data_mode"] == "mock"

    chain_response = client.get("/underlyings/SPY/chains")
    assert chain_response.status_code == 200
    chain = chain_response.json()
    assert chain["market_data_mode"] == "mock"
    assert len(chain["expirations"]) == 5

    quote = next(
        item
        for item in chain["calls"]
        if item["mark"] is not None
        and item["implied_vol"] is not None
        and not {"unusable_mark", "crossed_market", "stale"}.intersection(item["data_flags"])
    )
    contract_id = quote["contract"]["contract_id"]
    quote_response = client.get(f"/options/{contract_id}/quote")
    assert quote_response.status_code == 200
    assert quote_response.json()["quote_source"] == "mock"

    strategy = {
        "name": "Mock Long Call",
        "underlying_symbol": "SPY",
        "underlying_price": chain["underlying"]["spot"],
        "legs": [
            {
                "leg_id": "mock-leg",
                "instrument_type": "option",
                "side": "long",
                "quantity": 1,
                "contract": quote["contract"],
                "quote": quote,
                "entry_price": quote["mark"],
            }
        ],
    }
    pricing = client.post(
        "/strategies/price",
        json={
            "strategy": strategy,
            "assumptions": {
                "valuation_date": "2026-07-31",
                "underlying_price": chain["underlying"]["spot"],
                "risk_free_rate": 0.0425,
                "dividend_yield": 0.012,
                "days_forward": 0,
            },
        },
    )
    assert pricing.status_code == 200
    assert pricing.json()["payoff"]
    assert pricing.json()["max_profit_state"] == "unlimited"

    scenarios = client.post(
        "/strategies/scenario-grid",
        json={
            "strategy": strategy,
            "scenario": {
                "underlying_moves_pct": [-0.1, 0, 0.1],
                "implied_vol_shifts": [-0.05, 0, 0.05],
                "days_forward": [0, 7],
                "risk_free_rate": 0.0425,
                "dividend_yield": 0.012,
            },
        },
    )
    assert scenarios.status_code == 200
    assert len(scenarios.json()["points"]) == 18

    saved = client.post(
        "/workspace/strategies",
        json={"name": strategy["name"], "strategy": strategy},
    )
    assert saved.status_code == 200
    strategy_id = saved.json()["strategy_id"]

    reloaded = client.get("/workspace/strategies")
    assert reloaded.status_code == 200
    assert reloaded.json()[0]["strategy_id"] == strategy_id
    assert reloaded.json()[0]["strategy"]["legs"][0]["quote"]["quote_source"] == "mock"

    deleted = client.delete(f"/workspace/strategies/{strategy_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True}
