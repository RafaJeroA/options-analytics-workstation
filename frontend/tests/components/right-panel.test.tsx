import { render, screen } from "@testing-library/react";

import { RightPanel } from "@/components/layout/right-panel";
import type { PricingAssumptions } from "@/lib/types";

const assumptions: PricingAssumptions = {
  underlying_price: 215,
  risk_free_rate: 0.0425,
  dividend_yield: 0.005,
  volatility_shift: 0,
  days_forward: 0,
};

function renderPanel(stagedLegCount: number) {
  return render(
    <RightPanel
      assumptions={assumptions}
      hasStrategy={stagedLegCount > 0}
      stagedLegCount={stagedLegCount}
      onUpdateAssumptions={vi.fn()}
      onAddSelectedLong={vi.fn()}
      onAddSelectedShort={vi.fn()}
    />
  );
}

test("inspector distinguishes one staged leg from contract selection", () => {
  renderPanel(1);

  expect(screen.getByText(/No contract selected\. 1 staged leg remains active in Strategy/)).toBeInTheDocument();
  expect(screen.queryByText("Stage a strategy to populate the snapshot.")).not.toBeInTheDocument();
});

test("inspector pluralizes multiple staged legs", () => {
  renderPanel(2);

  expect(screen.getByText(/No contract selected\. 2 staged legs remain active in Strategy/)).toBeInTheDocument();
});

test("inspector gives an unambiguous empty instruction when nothing is staged", () => {
  renderPanel(0);

  expect(
    screen.getByText("No contract selected. Select a chain row to inspect and stage it.")
  ).toBeInTheDocument();
  expect(screen.getByText("Stage a strategy to populate the snapshot.")).toBeInTheDocument();
});

test("inspector renders unavailable mixed-expiration bounds with the specific reason", () => {
  const reason =
    "Exact single-spot expiry payoff, global bounds, and breakevens are unavailable for multiple option expirations because settlement spots can differ.";
  render(
    <RightPanel
      assumptions={assumptions}
      hasStrategy
      valuation={{
        strategy_name: "Call Calendar",
        underlying_symbol: "SPY",
        assumptions,
        net_debit_credit: -200,
        entry_cost: 200,
        current_value: 240,
        theoretical_value: 230,
        pnl_open: 40,
        max_profit: null,
        max_loss: null,
        max_profit_state: "unavailable",
        max_loss_state: "unavailable",
        payoff_unavailable_reason: reason,
        breakevens: [],
        breakeven_intervals: [],
        payoff: [],
        legs: [],
        pricing_state: "partial",
        status_message: reason,
        warnings: [reason],
      }}
      onUpdateAssumptions={vi.fn()}
      onAddSelectedLong={vi.fn()}
      onAddSelectedShort={vi.fn()}
    />
  );

  expect(screen.getAllByText("Unavailable")).toHaveLength(2);
  expect(screen.getByText(reason)).toBeInTheDocument();
});
