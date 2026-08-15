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
