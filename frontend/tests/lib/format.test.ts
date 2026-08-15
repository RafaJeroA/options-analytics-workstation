import {
  formatMarketDataMode,
  formatNumber,
  formatPayoffMetric,
  formatPercent,
  formatPrice,
  formatSignedNumber,
  formatSignedPercent,
} from "@/lib/format";
import type { MarketDataMode } from "@/lib/types";

test.each([Number.NaN, Number.POSITIVE_INFINITY, Number.NEGATIVE_INFINITY])(
  "all numeric formatters hide non-finite input %s",
  (value) => {
    expect(formatPrice(value)).toBe("--");
    expect(formatPercent(value)).toBe("--");
    expect(formatSignedPercent(value)).toBe("--");
    expect(formatSignedNumber(value)).toBe("--");
    expect(formatNumber(value)).toBe("--");
  }
);

test("payoff metrics render only their explicit state", () => {
  expect(formatPayoffMetric(null, "unlimited")).toBe("Unlimited");
  expect(formatPayoffMetric(-500, "finite")).toBe("-$500.00");
  expect(formatPayoffMetric(0, "unavailable")).toBe("Unavailable");
});

test.each<[MarketDataMode, string]>([
  ["live", "IBKR · LIVE"],
  ["frozen", "IBKR · FROZEN"],
  ["delayed", "IBKR · DELAYED"],
  ["delayed_frozen", "IBKR · DELAYED FROZEN"],
])("market data mode %s has an exact visible provenance label", (mode, expected) => {
  expect(formatMarketDataMode(mode)).toBe(expected);
  expect(formatMarketDataMode(mode)).not.toMatch(/NaN|Infinity/);
});
