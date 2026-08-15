import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";

import { defaultChainFilters } from "@/lib/chain";
import { useWorkstationStore } from "@/hooks/use-workstation-store";
import { WorkstationShell } from "@/components/layout/workstation-shell";
import { api } from "@/lib/api";

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
      timestamp: "2026-03-26T18:00:00Z",
      market_data_mode: "delayed",
      is_delayed: true,
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
        timestamp: "2026-03-26T18:00:00Z",
        market_data_mode: "delayed",
        is_delayed: true,
      },
      expirations: ["2026-04-17", "2026-05-15"],
      selected_expiration: "2026-04-17",
      updated_at: "2026-03-26T18:00:00Z",
      market_data_mode: "delayed",
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
    priceStrategy: vi.fn(async () => {
      throw new Error("not used");
    }),
    scenarioGrid: vi.fn(async () => {
      throw new Error("not used");
    }),
    addWatchlist: vi.fn(async () => ({
      symbol: "SPY",
      created_at: "2026-03-26T18:00:00Z",
    })),
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

vi.mock("@/components/strategy/strategy-builder", () => ({
  StrategyBuilder: () => <div>StrategyBuilder</div>,
}));

vi.mock("@/components/layout/right-panel", () => ({
  RightPanel: () => <div>RightPanel</div>,
}));

vi.mock("@/components/analytics/volatility-panel", () => ({
  VolatilityPanel: () => <div>VolatilityPanel</div>,
}));

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
    assumptions: {
      underlying_price: 0,
      risk_free_rate: 0.0425,
      dividend_yield: 0,
      volatility_shift: 0,
      days_forward: 0,
    },
    filters: defaultChainFilters,
  });
}

function wrapper({ children }: { children: React.ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  resetStore();
});

afterEach(() => {
  localStorage.clear();
  resetStore();
});

test("workstation shell replaces a stale persisted expiration with the backend-selected expiration", async () => {
  useWorkstationStore.setState({ selectedExpiration: "2026-01-16" });

  await act(async () => {
    render(<WorkstationShell />, { wrapper });
  });

  await waitFor(() => {
    expect(useWorkstationStore.getState().selectedExpiration).toBe("2026-04-17");
  });
});

test("workstation shell clears a stale selected contract when the active chain changes", async () => {
  useWorkstationStore.setState({
    selectedExpiration: "2026-01-16",
    selectedContract: {
      contract: {
        contract_id: "SPY-2026-01-16-500.00-C",
        symbol: "SPY",
        exchange: "SMART",
        currency: "USD",
        expiration: "2026-01-16",
        strike: 500,
        right: "call",
        multiplier: 100,
      },
      bid: 5,
      ask: 5.2,
      last: 5.1,
      mark: 5.1,
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
    },
  });

  await act(async () => {
    render(<WorkstationShell />, { wrapper });
  });

  await waitFor(() => {
    expect(useWorkstationStore.getState().selectedContract).toBeUndefined();
  });
});

test("workstation shell requests skew with the canonical chain expiration after fallback", async () => {
  useWorkstationStore.setState({
    selectedExpiration: "2026-01-16",
    activeView: "analytics",
  });

  await act(async () => {
    render(<WorkstationShell />, { wrapper });
  });

  await waitFor(() => {
    expect(vi.mocked(api.getVolSkew)).toHaveBeenCalledWith("SPY", "2026-04-17");
  });
  expect(vi.mocked(api.getVolSkew)).not.toHaveBeenCalledWith("SPY", "2026-01-16");
});

test("workstation shell uses singular staged-leg microcopy", async () => {
  useWorkstationStore.setState({
    strategy: {
      name: "Stock",
      underlying_symbol: "SPY",
      underlying_price: 500,
      legs: [
        {
          leg_id: "stock",
          instrument_type: "stock",
          side: "long",
          quantity: 1,
          underlying_symbol: "SPY",
          stock_price: 500,
          entry_price: 500,
        },
      ],
    },
  });

  await act(async () => {
    render(<WorkstationShell />, { wrapper });
  });

  expect(screen.getByText("1 leg staged")).toBeInTheDocument();
  expect(screen.queryByText("1 legs staged")).not.toBeInTheDocument();
});
