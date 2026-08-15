import { buildChainRows, defaultChainFilters, getSpreadPct } from "@/lib/chain";
import type { ChainSnapshot, OptionQuote } from "@/lib/types";

function makeQuote(
  contractId: string,
  strike: number,
  right: "call" | "put",
  overrides: Partial<OptionQuote> = {}
): OptionQuote {
  return {
    contract: {
      contract_id: contractId,
      symbol: "SPY",
      exchange: "SMART",
      currency: "USD",
      expiration: "2026-04-17",
      strike,
      right,
      multiplier: 100,
    },
    bid: 5,
    ask: 5.2,
    last: 5.1,
    mark: 5.1,
    model_price: 5.05,
    volume: 100,
    open_interest: 200,
    implied_vol: 0.24,
    broker_implied_vol: null,
    greeks: {
      delta: right === "call" ? 0.45 : -0.45,
      gamma: 0.04,
      theta: -0.08,
      vega: 0.18,
      rho: 0.06,
      theoretical_price: 5.05,
      source: "local_model",
    },
    intrinsic_value: 0,
    extrinsic_value: 5.1,
    data_flags: [],
    quote_source: "broker",
    model_source: "local_model",
    market_data_mode: "delayed",
    updated_at: "2026-03-26T18:00:00Z",
    is_delayed: true,
    ...overrides,
  };
}

const chain: ChainSnapshot = {
  symbol: "SPY",
  underlying: {
    symbol: "SPY",
    description: "SPDR S&P 500 ETF",
    exchange: "ARCA",
    currency: "USD",
    spot: 500,
    previous_close: 498,
    change: 2,
    change_percent: 0.4,
    timestamp: "2026-03-26T18:00:00Z",
    market_data_mode: "delayed",
    is_delayed: true,
  },
  expirations: ["2026-04-17"],
  selected_expiration: "2026-04-17",
  updated_at: "2026-03-26T18:00:00Z",
  market_data_mode: "delayed",
  calls: [
    makeQuote("SPY-2026-04-17-500.00-C", 500, "call", { greeks: { ...makeQuote("", 500, "call").greeks!, delta: 0.82 } }),
    makeQuote("SPY-2026-04-17-510.00-C", 510, "call"),
  ],
  puts: [
    makeQuote("SPY-2026-04-17-500.00-P", 500, "put"),
    makeQuote("SPY-2026-04-17-510.00-P", 510, "put", { bid: 6.1, ask: 5.9, mark: null }),
  ],
};

test("spread helper treats missing and crossed markets as unusable", () => {
  expect(getSpreadPct(undefined)).toBe(Infinity);
  expect(getSpreadPct(makeQuote("SPY-2026-04-17-495.00-C", 495, "call", { bid: null, ask: 4.2 }))).toBe(Infinity);
  expect(getSpreadPct(makeQuote("SPY-2026-04-17-505.00-P", 505, "put", { bid: 3.2, ask: 3.0, mark: null }))).toBe(
    Infinity
  );
});

test("delta filtering preserves the row when only one side passes", () => {
  const rows = buildChainRows(
    chain,
    {
      ...defaultChainFilters,
      deltaMin: -0.6,
      deltaMax: 0.6,
    },
    []
  );

  const atmRow = rows.find((row) => row.strike === 500);
  expect(atmRow).toBeDefined();
  expect(atmRow?.call).toBeUndefined();
  expect(atmRow?.put?.contract.contract_id).toBe("SPY-2026-04-17-500.00-P");
});

test("spread filtering removes only the invalid side of a paired row", () => {
  const rows = buildChainRows(chain, defaultChainFilters, []);

  const row = rows.find((item) => item.strike === 510);
  expect(row).toBeDefined();
  expect(row?.call?.contract.contract_id).toBe("SPY-2026-04-17-510.00-C");
  expect(row?.put).toBeUndefined();
});
