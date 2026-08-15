import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ChainExplorer } from "@/components/chain/chain-explorer";
import { defaultChainFilters } from "@/lib/chain";
import type { ChainSnapshot } from "@/lib/types";

const chain: ChainSnapshot = {
  symbol: "SPY",
  underlying: {
    symbol: "SPY",
    description: "SPDR S&P 500 ETF",
    exchange: "ARCA",
    currency: "USD",
    spot: 500,
    previous_close: 495,
    change: 5,
    change_percent: 1.01,
    timestamp: "2026-03-26T18:00:00Z",
    market_data_mode: "delayed",
    is_delayed: true,
  },
  expirations: ["2026-04-17"],
  selected_expiration: "2026-04-17",
  updated_at: "2026-03-26T18:00:00Z",
  market_data_mode: "delayed",
  calls: [
    {
      contract: {
        contract_id: "SPY-2026-04-17-500.00-C",
        symbol: "SPY",
        exchange: "SMART",
        currency: "USD",
        expiration: "2026-04-17",
        strike: 500,
        right: "call",
        multiplier: 100,
      },
      bid: 10,
      ask: 10.5,
      last: 10.2,
      mark: 10.25,
      model_price: 10.1,
      volume: 500,
      open_interest: 1000,
      implied_vol: 0.24,
      broker_implied_vol: null,
      greeks: { delta: 0.52, gamma: 0.04, theta: -0.1, vega: 0.2, rho: 0.1, theoretical_price: 10.1, source: "local_model" },
      intrinsic_value: 0,
      extrinsic_value: 10.25,
      data_flags: [],
      quote_source: "broker",
      model_source: "local_model",
      market_data_mode: "delayed",
      updated_at: "2026-03-26T18:00:00Z",
      is_delayed: true,
    },
  ],
  puts: [
    {
      contract: {
        contract_id: "SPY-2026-04-17-500.00-P",
        symbol: "SPY",
        exchange: "SMART",
        currency: "USD",
        expiration: "2026-04-17",
        strike: 500,
        right: "put",
        multiplier: 100,
      },
      bid: 9.8,
      ask: 10.3,
      last: 10,
      mark: 10.05,
      model_price: 10,
      volume: 450,
      open_interest: 900,
      implied_vol: 0.26,
      broker_implied_vol: null,
      greeks: { delta: -0.48, gamma: 0.04, theta: -0.11, vega: 0.22, rho: -0.1, theoretical_price: 10, source: "local_model" },
      intrinsic_value: 0,
      extrinsic_value: 10.05,
      data_flags: [],
      quote_source: "broker",
      model_source: "local_model",
      market_data_mode: "delayed",
      updated_at: "2026-03-26T18:00:00Z",
      is_delayed: true,
    },
  ],
};

test("chain explorer renders rows and forwards action handlers", async () => {
  const user = userEvent.setup();
  const addLong = vi.fn();

  render(
    <ChainExplorer
      chain={chain}
      selectedExpiration="2026-04-17"
      filters={defaultChainFilters}
      pinnedContracts={[]}
      onSelectExpiration={vi.fn()}
      onSelectContract={vi.fn()}
      onAddLong={addLong}
      onAddShort={vi.fn()}
      onTogglePinned={vi.fn()}
      onUpdateFilters={vi.fn()}
    />
  );

  expect(screen.getByText("500.00")).toBeInTheDocument();
  await user.click(screen.getAllByRole("button")[1]);
  expect(addLong).toHaveBeenCalled();
});

test("chain explorer shows a bounded loading state when chain data is not ready", () => {
  render(
    <ChainExplorer
      chain={undefined}
      selectedExpiration={undefined}
      filters={defaultChainFilters}
      pinnedContracts={[]}
      loading
      onSelectExpiration={vi.fn()}
      onSelectContract={vi.fn()}
      onAddLong={vi.fn()}
      onAddShort={vi.fn()}
      onTogglePinned={vi.fn()}
      onUpdateFilters={vi.fn()}
    />
  );

  expect(screen.getByText("Loading option chain...")).toBeInTheDocument();
});
