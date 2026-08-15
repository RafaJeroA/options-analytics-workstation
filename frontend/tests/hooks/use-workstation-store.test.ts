import { defaultChainFilters } from "@/lib/chain";
import { useWorkstationStore } from "@/hooks/use-workstation-store";
import type { ChainSnapshot, OptionQuote } from "@/lib/types";

const baseAssumptionsForTest = {
  underlying_price: 0,
  risk_free_rate: 0.0425,
  dividend_yield: 0,
  volatility_shift: 0,
  days_forward: 0,
};

function resetStore() {
  useWorkstationStore.setState({
    symbol: "SPY",
    selectedExpiration: undefined,
    selectedContract: undefined,
    activeView: "chain",
    watchlistSymbols: ["SPY", "AAPL", "QQQ"],
    pinnedContracts: [],
    strategy: {
      name: "Custom Strategy",
      underlying_symbol: "SPY",
      underlying_price: 0,
      legs: [],
    },
    assumptions: baseAssumptionsForTest,
    filters: defaultChainFilters,
  });
}

function buildQuote(contractId: string, expiration: string, mark = 5.1): OptionQuote {
  return {
    contract: {
      contract_id: contractId,
      symbol: "SPY",
      exchange: "SMART",
      currency: "USD",
      expiration,
      strike: 500,
      right: contractId.endsWith("-P") ? "put" : "call",
      multiplier: 100,
    },
    bid: 5,
    ask: 5.2,
    last: 5.1,
    mark,
    model_price: 5.05,
    volume: 10,
    open_interest: 20,
    implied_vol: 0.22,
    broker_implied_vol: 0.22,
    greeks: {
      delta: 0.5,
      gamma: 0.02,
      theta: -0.03,
      vega: 0.11,
      rho: 0.04,
      theoretical_price: 5.05,
      source: "broker_model",
    },
    intrinsic_value: 0,
    extrinsic_value: 5.1,
    data_flags: [],
    quote_source: "broker",
    model_source: "broker_model",
    market_data_mode: "delayed",
    updated_at: "2026-03-26T18:00:00Z",
    is_delayed: true,
  };
}

function buildChain(selectedExpiration: string, calls: OptionQuote[]): ChainSnapshot {
  return {
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
    expirations: ["2026-04-17", "2026-05-15"],
    selected_expiration: selectedExpiration,
    calls,
    puts: [],
    updated_at: "2026-03-26T18:00:00Z",
    market_data_mode: "delayed",
  };
}

beforeEach(() => {
  localStorage.clear();
  resetStore();
});

afterEach(() => {
  localStorage.clear();
  resetStore();
});

test("store persistence writes current strategy and workspace selections", () => {
  const store = useWorkstationStore.getState();

  store.setSymbol("qqq");
  store.setSelectedExpiration("2026-04-17");
  store.setActiveView("strategy");
  store.replaceStrategy("Long Call", [
    {
      leg_id: "leg-1",
      instrument_type: "stock",
      side: "long",
      quantity: 100,
      underlying_symbol: "QQQ",
      stock_price: 500,
      entry_price: 500,
    },
  ]);
  store.updateAssumptions({ risk_free_rate: 0.03, days_forward: 5 });
  store.updateFilters({ maxSpreadPct: 0.12 });

  const persisted = JSON.parse(localStorage.getItem("modellator-workstation") ?? "{}");

  expect(persisted.state.symbol).toBe("QQQ");
  expect(persisted.state.selectedExpiration).toBe("2026-04-17");
  expect(persisted.state.activeView).toBe("strategy");
  expect(persisted.state.strategy.name).toBe("Long Call");
  expect(persisted.state.strategy.legs).toHaveLength(1);
  expect(persisted.state.assumptions.risk_free_rate).toBe(0.03);
  expect(persisted.state.filters.maxSpreadPct).toBe(0.12);
});

test("store persistence rehydrates the current strategy from storage", async () => {
  resetStore();
  localStorage.setItem(
    "modellator-workstation",
    JSON.stringify({
      state: {
        symbol: "AAPL",
        selectedExpiration: "2026-05-15",
        activeView: "strategy",
        watchlistSymbols: ["AAPL"],
        pinnedContracts: ["AAPL-2026-05-15-210.00-C"],
        strategy: {
          name: "Reloaded Strategy",
          underlying_symbol: "AAPL",
          underlying_price: 210,
          legs: [
            {
              leg_id: "leg-9",
              instrument_type: "option",
              side: "short",
              quantity: 1,
              contract: {
                contract_id: "AAPL-2026-05-15-210.00-C",
                symbol: "AAPL",
                exchange: "SMART",
                currency: "USD",
                expiration: "2026-05-15",
                strike: 210,
                right: "call",
                multiplier: 100,
              },
            },
          ],
        },
        assumptions: {
          underlying_price: 210,
          risk_free_rate: 0.028,
          dividend_yield: 0.01,
          volatility_shift: 0.02,
          days_forward: 3,
        },
        filters: {
          ...defaultChainFilters,
          maxSpreadPct: 0.08,
        },
      },
      version: 0,
    })
  );

  await useWorkstationStore.persist.rehydrate();

  const state = useWorkstationStore.getState();
  expect(state.symbol).toBe("AAPL");
  expect(state.selectedExpiration).toBe("2026-05-15");
  expect(state.activeView).toBe("strategy");
  expect(state.strategy.name).toBe("Reloaded Strategy");
  expect(state.strategy.legs).toHaveLength(1);
  expect(state.filters.maxSpreadPct).toBe(0.08);
});

test("selecting the same symbol keeps the active expiry intact", () => {
  const store = useWorkstationStore.getState();

  store.setSelectedExpiration("2026-04-17");
  store.setSymbol("SPY");

  expect(useWorkstationStore.getState().selectedExpiration).toBe("2026-04-17");
});

test("changing symbols clears incompatible strategy legs and underlying state", () => {
  const store = useWorkstationStore.getState();
  store.syncUnderlying("SPY", 500);
  store.addStrategyLeg({
    leg_id: "stock-spy",
    instrument_type: "stock",
    side: "long",
    quantity: 100,
    underlying_symbol: "SPY",
    stock_price: 500,
    entry_price: 500,
  });

  store.setSymbol("AAPL");

  const state = useWorkstationStore.getState();
  expect(state.symbol).toBe("AAPL");
  expect(state.strategy).toEqual({
    name: "Custom Strategy",
    underlying_symbol: "AAPL",
    underlying_price: 0,
    legs: [],
  });
  expect(state.assumptions.underlying_price).toBe(0);
});

test("rehydration discards a strategy whose legs belong to another symbol", async () => {
  localStorage.setItem(
    "modellator-workstation",
    JSON.stringify({
      state: {
        symbol: "AAPL",
        strategy: {
          name: "Stale SPY call",
          underlying_symbol: "AAPL",
          underlying_price: 200,
          legs: [
            {
              leg_id: "wrong-symbol",
              instrument_type: "option",
              side: "long",
              quantity: 1,
              contract: buildQuote("SPY-2026-04-17-500.00-C", "2026-04-17").contract,
            },
          ],
        },
        assumptions: { ...baseAssumptionsForTest, underlying_price: 200 },
      },
      version: 0,
    })
  );

  await useWorkstationStore.persist.rehydrate();

  expect(useWorkstationStore.getState().strategy.legs).toEqual([]);
  expect(useWorkstationStore.getState().strategy.underlying_symbol).toBe("AAPL");
});

test("reconcileChainSelection replaces a stale expiration and clears a stale contract", () => {
  const store = useWorkstationStore.getState();
  const staleQuote = buildQuote("SPY-2026-01-16-500.00-C", "2026-01-16");

  store.setSelectedExpiration("2026-01-16");
  store.setSelectedContract(staleQuote);
  store.reconcileChainSelection(buildChain("2026-04-17", [buildQuote("SPY-2026-04-17-500.00-C", "2026-04-17")]));

  expect(useWorkstationStore.getState().selectedExpiration).toBe("2026-04-17");
  expect(useWorkstationStore.getState().selectedContract).toBeUndefined();
});

test("reconcileChainSelection refreshes the selected contract from the active chain", () => {
  const initialQuote = buildQuote("SPY-2026-04-17-500.00-C", "2026-04-17", 5.1);
  const refreshedQuote = buildQuote("SPY-2026-04-17-500.00-C", "2026-04-17", 5.6);
  const store = useWorkstationStore.getState();

  store.setSelectedExpiration("2026-04-17");
  store.setSelectedContract(initialQuote);
  store.reconcileChainSelection(buildChain("2026-04-17", [refreshedQuote]));

  expect(useWorkstationStore.getState().selectedContract?.mark).toBe(5.6);
});
