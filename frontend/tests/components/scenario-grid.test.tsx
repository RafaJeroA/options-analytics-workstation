import { fireEvent, render, screen } from "@testing-library/react";

import { ScenarioGrid, scenarioCellKey } from "@/components/analytics/scenario-grid";
import type { ScenarioGridResult, ScenarioPoint } from "@/lib/types";

function point(days: number, shift: number, pnl: number): ScenarioPoint {
  return {
    underlying_price: 500,
    move_pct: 0,
    vol_shift: shift,
    days_forward: days,
    current_value: pnl,
    theoretical_value: pnl,
    pnl_open: pnl,
  };
}

const scenario: ScenarioGridResult = {
  strategy_name: "Long Call",
  underlying_symbol: "SPY",
  base_underlying_price: 500,
  points: [point(0, 0, 100), point(7, 0, 200)],
  pricing_state: "complete",
  status_message: null,
  warnings: [],
  volatility_shift_effective: true,
  day_states: [
    {
      days_forward: 0,
      expiration_state: "pre_expiry",
      volatility_shift_effective: true,
      message: null,
    },
    {
      days_forward: 7,
      expiration_state: "pre_expiry",
      volatility_shift_effective: true,
      message: null,
    },
  ],
};

test("scenario cells remain distinct across forward days", () => {
  render(<ScenarioGrid scenario={scenario} hasStrategy />);

  expect(screen.getByText("$100.00")).toBeInTheDocument();
  expect(document.querySelector(`[data-scenario-key="${scenarioCellKey(0, 0, 0)}"]`)).toBeTruthy();
  fireEvent.click(screen.getByRole("button", { name: "+7d" }));
  expect(screen.getByText("$200.00")).toBeInTheDocument();
  expect(screen.queryByText("$100.00")).not.toBeInTheDocument();
  expect(document.querySelector(`[data-scenario-key="${scenarioCellKey(7, 0, 0)}"]`)).toBeTruthy();
});

test("pre-expiry volatility columns retain distinct values", () => {
  const preExpiry = {
    ...scenario,
    points: [point(0, -0.1, 80), point(0, 0, 100), point(0, 0.1, 125)],
  };
  render(<ScenarioGrid scenario={preExpiry} hasStrategy />);

  expect(screen.getByText("-10%")).toBeInTheDocument();
  expect(screen.getByText("+10%")).toBeInTheDocument();
  expect(screen.getByText("$80.00")).toBeInTheDocument();
  expect(screen.getByText("$125.00")).toBeInTheDocument();
});

test("at-expiry volatility columns collapse and explain why", () => {
  const expiryMessage =
    "At or after expiry: values reflect expiry payoff; volatility shifts have no effect. Post-expiry cash is carried at the risk-free rate.";
  const atExpiry: ScenarioGridResult = {
    ...scenario,
    points: [point(7, -0.1, 200), point(7, 0, 200), point(7, 0.1, 200)],
    volatility_shift_effective: false,
    day_states: [
      {
        days_forward: 7,
        expiration_state: "at_or_after_expiry",
        volatility_shift_effective: false,
        message: expiryMessage,
      },
    ],
  };
  render(<ScenarioGrid scenario={atExpiry} hasStrategy />);

  expect(screen.getByTestId("scenario-day-state")).toHaveTextContent(expiryMessage);
  expect(screen.getByText("Expiry payoff")).toBeInTheDocument();
  expect(screen.getAllByText("$200.00")).toHaveLength(1);
  expect(screen.queryByText("-10%")).not.toBeInTheDocument();
  expect(screen.queryByText("+10%")).not.toBeInTheDocument();
});

test("mixed-expiration tabs preserve their settlement explanation", () => {
  const mixed = {
    ...scenario,
    points: [point(0, 0, 100), point(7, -0.1, 180), point(7, 0, 200), point(7, 0.1, 220)],
    day_states: [
      scenario.day_states[0],
      {
        days_forward: 7,
        expiration_state: "mixed" as const,
        volatility_shift_effective: true,
        message:
          "Mixed expirations: expired legs use intrinsic settlement at the scenario spot and are carried to the scenario date at the risk-free rate; unexpired legs retain time value.",
      },
    ],
  };
  render(<ScenarioGrid scenario={mixed} hasStrategy />);

  fireEvent.click(screen.getByRole("button", { name: "+7d" }));
  expect(screen.getByTestId("scenario-day-state")).toHaveTextContent("Mixed expirations");
  expect(screen.getByText("-10%")).toBeInTheDocument();
  expect(screen.getByText("+10%")).toBeInTheDocument();
});

test("scenario cells never display non-finite PnL", () => {
  render(
    <ScenarioGrid
      hasStrategy
      scenario={{ ...scenario, points: [{ ...scenario.points[0], pnl_open: Number.POSITIVE_INFINITY }] }}
    />
  );

  expect(screen.getByText("--")).toBeInTheDocument();
  expect(screen.queryByText(/Infinity|NaN/)).not.toBeInTheDocument();
});
