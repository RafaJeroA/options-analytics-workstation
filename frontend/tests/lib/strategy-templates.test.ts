import { buildTemplate } from "@/lib/strategy-templates";
import type { ChainSnapshot, OptionQuote, OptionRight } from "@/lib/types";

function quote(strike: number, right: OptionRight, flags: OptionQuote["data_flags"] = []): OptionQuote {
  return {
    contract: {
      contract_id: `SPY-2026-08-21-${strike.toFixed(2)}-${right === "call" ? "C" : "P"}`,
      symbol: "SPY",
      exchange: "SMART",
      currency: "USD",
      expiration: "2026-08-21",
      strike,
      right,
      multiplier: 100,
    },
    bid: 4.9,
    ask: 5.1,
    last: 5,
    mark: 5,
    model_price: 5,
    volume: 100,
    open_interest: 500,
    implied_vol: 0.2,
    broker_implied_vol: null,
    greeks: null,
    intrinsic_value: 0,
    extrinsic_value: 5,
    data_flags: flags,
    quote_source: "mock",
    model_source: "local_model",
    market_data_mode: "mock",
    updated_at: "2026-07-31T15:30:00Z",
    is_delayed: false,
  };
}

function chain(strikes = [90, 95, 100, 105, 110]): ChainSnapshot {
  return {
    symbol: "SPY",
    underlying: {
      symbol: "SPY",
      description: "Synthetic SPY fixture",
      exchange: "ARCA",
      currency: "USD",
      spot: 100,
      previous_close: 99,
      change: 1,
      change_percent: 1.01,
      timestamp: "2026-07-31T15:30:00Z",
      market_data_mode: "mock",
      is_delayed: false,
    },
    expirations: ["2026-08-21"],
    selected_expiration: "2026-08-21",
    calls: strikes.map((strike) => quote(strike, "call")),
    puts: strikes.map((strike) => quote(strike, "put")),
    updated_at: "2026-07-31T15:30:00Z",
    market_data_mode: "mock",
  };
}

test("builds a standard ordered 1:-2:1 call butterfly", () => {
  const legs = buildTemplate(chain(), "butterfly");

  expect(legs.map((leg) => [leg.contract?.strike, leg.side, leg.quantity])).toEqual([
    [95, "long", 1],
    [100, "short", 2],
    [105, "long", 1],
  ]);
});

test("builds an iron condor with protective wings outside both short strikes", () => {
  const legs = buildTemplate(chain(), "iron_condor");

  expect(legs.map((leg) => [leg.contract?.right, leg.contract?.strike, leg.side])).toEqual([
    ["put", 90, "long"],
    ["put", 95, "short"],
    ["call", 105, "short"],
    ["call", 110, "long"],
  ]);
});

test("uses the nearest strictly out-of-the-money strikes for a strangle", () => {
  const legs = buildTemplate(chain(), "strangle");
  expect(legs.map((leg) => [leg.contract?.right, leg.contract?.strike])).toEqual([
    ["call", 105],
    ["put", 95],
  ]);
});

test("does not silently degrade multi-leg templates when required wings are unavailable", () => {
  const sparse = chain([95, 100, 105]);
  expect(buildTemplate(sparse, "iron_condor")).toEqual([]);

  const topCall = sparse.calls.at(-1);
  expect(buildTemplate(sparse, "vertical_spread", topCall)).toEqual([]);
});

test("excludes stale or crossed contracts from template legs", () => {
  const snapshot = chain();
  snapshot.calls = snapshot.calls.map((item) =>
    item.contract.strike === 105 ? quote(105, "call", ["crossed_market"]) : item
  );

  expect(buildTemplate(snapshot, "strangle").map((leg) => leg.contract?.strike)).toEqual([110, 95]);
});
