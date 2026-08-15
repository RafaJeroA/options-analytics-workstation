import { fireEvent, render, screen } from "@testing-library/react";

import { SavedStrategyPanel } from "@/components/strategy/saved-strategy-panel";
import type { SavedStrategyRecord } from "@/lib/types";

const record: SavedStrategyRecord = {
  strategy_id: "strategy-1",
  name: "Recruiter Demo Call",
  strategy: {
    name: "Recruiter Demo Call",
    underlying_symbol: "SPY",
    underlying_price: 500,
    legs: [
      {
        leg_id: "leg-1",
        instrument_type: "stock",
        side: "long",
        quantity: 100,
        underlying_symbol: "SPY",
        stock_price: 500,
        entry_price: 500,
      },
    ],
  },
  updated_at: "2026-07-31T15:30:00Z",
};

test("saved-strategy panel supports save load and delete actions", () => {
  const onSave = vi.fn();
  const onLoad = vi.fn();
  const onDelete = vi.fn();

  render(
    <SavedStrategyPanel
      records={[record]}
      canSave
      onSave={onSave}
      onLoad={onLoad}
      onDelete={onDelete}
      onRetry={vi.fn()}
    />
  );

  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  fireEvent.click(screen.getByRole("button", { name: "Load Recruiter Demo Call" }));
  fireEvent.click(screen.getByRole("button", { name: "Delete Recruiter Demo Call" }));

  expect(onSave).toHaveBeenCalledOnce();
  expect(onLoad).toHaveBeenCalledWith(record);
  expect(onDelete).toHaveBeenCalledWith("strategy-1");
});

test("saved-strategy panel distinguishes loading empty and retry states", () => {
  const onRetry = vi.fn();
  const { rerender } = render(
    <SavedStrategyPanel records={[]} loading onSave={vi.fn()} onLoad={vi.fn()} onDelete={vi.fn()} onRetry={onRetry} />
  );
  expect(screen.getByText("Loading saved strategies...")).toBeInTheDocument();

  rerender(
    <SavedStrategyPanel
      records={[]}
      errorMessage="Connection unavailable: local API offline"
      onSave={vi.fn()}
      onLoad={vi.fn()}
      onDelete={vi.fn()}
      onRetry={onRetry}
    />
  );
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(onRetry).toHaveBeenCalledOnce();
});
