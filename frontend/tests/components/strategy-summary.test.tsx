import { render, screen } from "@testing-library/react";

import { StrategySummary } from "@/components/strategy/strategy-summary";

test("strategy summary renders bounded and unbounded states", () => {
  render(
    <StrategySummary
      valuation={{
        strategy_name: "Bull Call Spread",
        underlying_symbol: "SPY",
        assumptions: {
          underlying_price: 500,
          risk_free_rate: 0.04,
          dividend_yield: 0,
          volatility_shift: 0,
          days_forward: 0,
        },
        net_debit_credit: -150,
        entry_cost: 150,
        current_value: 180,
        theoretical_value: 175,
        pnl_open: 30,
        max_profit: null,
        max_loss: -150,
        max_profit_state: "unavailable",
        max_loss_state: "finite",
        breakevens: [501.5],
        breakeven_intervals: [],
        payoff: [],
        legs: [],
        pricing_state: "partial",
        status_message: "Strategy pricing incomplete: one or more legs have no usable entry premium.",
        warnings: ["Strategy pricing incomplete: one or more legs have no usable entry premium."],
      }}
    />
  );

  expect(screen.getAllByText("Unavailable").length).toBeGreaterThan(0);
  expect(screen.getByText("$180.00")).toBeInTheDocument();
  expect(screen.getByText("Strategy pricing incomplete: one or more legs have no usable entry premium.")).toBeInTheDocument();
});

test("strategy summary trusts explicit unlimited states and never renders non-finite numbers", () => {
  render(
    <StrategySummary
      valuation={{
        strategy_name: "Long Call",
        underlying_symbol: "SPY",
        assumptions: {
          underlying_price: 500,
          risk_free_rate: 0.04,
          dividend_yield: 0,
          volatility_shift: 0,
          days_forward: 0,
        },
        net_debit_credit: -100,
        entry_cost: Number.NaN,
        current_value: Number.POSITIVE_INFINITY,
        theoretical_value: 110,
        pnl_open: 10,
        max_profit: null,
        max_loss: -100,
        max_profit_state: "unlimited",
        max_loss_state: "finite",
        breakevens: [501],
        breakeven_intervals: [],
        payoff: [],
        legs: [],
        pricing_state: "complete",
        status_message: null,
        warnings: [],
      }}
    />
  );

  expect(screen.getByText("Unlimited")).toBeInTheDocument();
  expect(screen.getByText("-$100.00")).toBeInTheDocument();
  expect(screen.queryByText(/NaN|Infinity/)).not.toBeInTheDocument();
});
