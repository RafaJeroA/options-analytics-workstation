import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";

import { WorkstationShell } from "@/components/layout/workstation-shell";
import { useWorkstationStore } from "@/hooks/use-workstation-store";
import type { StrategyDefinition, StrategyValuation } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  priceStrategy: vi.fn(),
}));

vi.mock("@/lib/api", () => ({
  apiErrorLabel: () => "Unavailable",
  apiErrorMessage: (_error: unknown, fallback: string) => fallback,
  isRetryableApiError: () => false,
  api: {
    getUnderlyingSummary: vi.fn(async () => ({
      symbol: "SPY",
      description: "SPDR S&P 500 ETF",
      exchange: "ARCA",
      currency: "USD",
      spot: 500,
      previous_close: 498,
      change: 2,
      change_percent: 0.4,
      timestamp: "2026-07-31T15:30:00Z",
      market_data_mode: "mock",
      is_delayed: false,
    })),
    getChain: vi.fn(async () => ({
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
        timestamp: "2026-07-31T15:30:00Z",
        market_data_mode: "mock",
        is_delayed: false,
      },
      expirations: ["2026-08-07", "2026-08-14"],
      selected_expiration: "2026-08-07",
      updated_at: "2026-07-31T15:30:00Z",
      market_data_mode: "mock",
      calls: [],
      puts: [],
    })),
    getWatchlist: vi.fn(async () => []),
    getSavedStrategies: vi.fn(async () => []),
    saveStrategyDefinition: vi.fn(async () => {
      throw new Error("not used");
    }),
    deleteSavedStrategy: vi.fn(async () => ({ deleted: true })),
    getVolSkew: vi.fn(async () => []),
    getTermStructure: vi.fn(async () => []),
    priceStrategy: mocks.priceStrategy,
    scenarioGrid: vi.fn(async () => {
      throw new Error("not used");
    }),
    addWatchlist: vi.fn(async () => ({ symbol: "SPY", created_at: "2026-07-31T15:30:00Z" })),
  },
}));

vi.mock("@/hooks/use-market-streams", () => ({
  useMarketStreams: () => ({
    quoteStatus: { state: "idle", message: undefined },
    chainStatus: { state: "idle", message: undefined },
  }),
}));

vi.mock("@/components/layout/sidebar", () => ({
  Sidebar: () => <div>Sidebar</div>,
}));

vi.mock("@/components/chain/chain-explorer", () => ({
  ChainExplorer: () => <div>ChainExplorer</div>,
}));

vi.mock("@/components/analytics/volatility-panel", () => ({
  VolatilityPanel: () => <div>VolatilityPanel</div>,
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: unknown) => void;
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function optionLeg(expiration: string, legId: string): StrategyDefinition["legs"][number] {
  const contract = {
    contract_id: `SPY-${expiration}-500-${legId}`,
    symbol: "SPY",
    exchange: "SMART",
    currency: "USD",
    expiration,
    strike: 500,
    right: "call" as const,
    multiplier: 100,
  };
  const quote = {
    contract,
    bid: 5,
    ask: 5.2,
    last: 5.1,
    mark: 5.1,
    model_price: 5.1,
    volume: 100,
    open_interest: 1000,
    implied_vol: 0.24,
    broker_implied_vol: 0.24,
    greeks: null,
    intrinsic_value: 0,
    extrinsic_value: 5.1,
    data_flags: [],
    quote_source: "mock" as const,
    model_source: "mock" as const,
    market_data_mode: "mock" as const,
    updated_at: "2026-07-31T15:30:00Z",
    is_delayed: false,
  };
  return {
    leg_id: legId,
    instrument_type: "option",
    side: legId === "near" ? "short" : "long",
    quantity: 1,
    contract,
    quote,
    entry_price: 5.1,
  };
}

const sameExpirationStrategy: StrategyDefinition = {
  name: "Long Call",
  underlying_symbol: "SPY",
  underlying_price: 500,
  legs: [optionLeg("2026-08-07", "near")],
};

const mixedExpirationStrategy: StrategyDefinition = {
  ...sameExpirationStrategy,
  name: "Call Calendar",
  legs: [optionLeg("2026-08-07", "near"), optionLeg("2026-08-14", "far")],
};

function valuation(mixed: boolean): StrategyValuation {
  const reason =
    "Exact single-spot expiry payoff, global bounds, and breakevens are unavailable for multiple option expirations because settlement spots can differ.";
  return {
    strategy_name: mixed ? "Call Calendar" : "Long Call",
    underlying_symbol: "SPY",
    assumptions: {
      valuation_date: "2026-07-31",
      underlying_price: 500,
      risk_free_rate: 0.0425,
      dividend_yield: 0,
      volatility_shift: 0,
      days_forward: 0,
    },
    net_debit_credit: mixed ? -1020 : -510,
    entry_cost: mixed ? 1020 : 510,
    current_value: mixed ? 1030 : 600,
    theoretical_value: mixed ? 1010 : 700,
    pnl_open: mixed ? 10 : 90,
    max_profit: null,
    max_loss: mixed ? null : -510,
    max_profit_state: mixed ? "unavailable" : "unlimited",
    max_loss_state: mixed ? "unavailable" : "finite",
    payoff_unavailable_reason: mixed ? reason : null,
    breakevens: mixed ? [] : [505.1],
    breakeven_intervals: [],
    payoff: mixed ? [] : [{ spot: 500, value: -510 }, { spot: 600, value: 9490 }],
    legs: [],
    pricing_state: mixed ? "partial" : "complete",
    status_message: mixed ? reason : null,
    warnings: mixed ? [reason] : [],
  };
}

function resetStore(strategy: StrategyDefinition) {
  useWorkstationStore.setState({
    symbol: "SPY",
    selectedExpiration: "2026-08-07",
    selectedContract: undefined,
    activeView: "strategy",
    watchlistSymbols: ["SPY"],
    pinnedContracts: [],
    strategy,
    assumptions: {
      valuation_date: "2026-07-31",
      underlying_price: 500,
      risk_free_rate: 0.0425,
      dividend_yield: 0,
      volatility_shift: 0,
      days_forward: 0,
    },
  });
}

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
});

afterEach(() => {
  localStorage.clear();
  resetStore(sameExpirationStrategy);
});

test("hides old exact metrics during a delayed mixed-expiration response", async () => {
  const same = deferred<StrategyValuation>();
  const mixed = deferred<StrategyValuation>();
  mocks.priceStrategy.mockImplementation((strategy: StrategyDefinition) =>
    new Set(
      strategy.legs
        .filter((leg) => leg.instrument_type === "option")
        .map((leg) => leg.contract?.expiration)
    ).size > 1
      ? mixed.promise
      : same.promise
  );
  resetStore(sameExpirationStrategy);

  render(<WorkstationShell />, { wrapper });
  await waitFor(() => expect(mocks.priceStrategy).toHaveBeenCalled());
  same.resolve(valuation(false));
  await waitFor(() => expect(screen.getAllByText("Unlimited").length).toBeGreaterThan(0));

  act(() => {
    useWorkstationStore.setState({ strategy: mixedExpirationStrategy });
  });

  await waitFor(() => expect(screen.queryByText("$1,000.00")).not.toBeInTheDocument());
  expect(screen.queryByText("Unlimited")).not.toBeInTheDocument();

  await waitFor(() => {
    expect(mocks.priceStrategy).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Call Calendar" }),
      expect.anything()
    );
  });
  mixed.resolve(valuation(true));

  await waitFor(() => expect(screen.getAllByText("Unavailable").length).toBeGreaterThanOrEqual(3));
  expect(screen.getAllByText(/settlement spots can differ/).length).toBeGreaterThan(0);
  expect(screen.getAllByText(/Exact single-spot expiry payoff/).length).toBeGreaterThan(0);
});

test("late old responses do not restore exact metrics after the current request fails", async () => {
  const same = deferred<StrategyValuation>();
  const mixed = deferred<StrategyValuation>();
  mocks.priceStrategy.mockImplementation((strategy: StrategyDefinition) =>
    new Set(
      strategy.legs
        .filter((leg) => leg.instrument_type === "option")
        .map((leg) => leg.contract?.expiration)
    ).size > 1
      ? mixed.promise
      : same.promise
  );
  resetStore(sameExpirationStrategy);

  render(<WorkstationShell />, { wrapper });
  await waitFor(() => expect(mocks.priceStrategy).toHaveBeenCalled());
  act(() => {
    useWorkstationStore.setState({ strategy: mixedExpirationStrategy });
  });
  same.resolve(valuation(false));

  await waitFor(() => {
    expect(mocks.priceStrategy).toHaveBeenCalledWith(
      expect.objectContaining({ name: "Call Calendar" }),
      expect.anything()
    );
  });
  expect(screen.queryByText("Unlimited")).not.toBeInTheDocument();
  mixed.reject(new Error("current request failed"));

  await waitFor(() => expect(screen.getByText("Unavailable: Strategy pricing unavailable.")).toBeInTheDocument());
  expect(screen.queryByText("Unlimited")).not.toBeInTheDocument();
});
