import { render, screen } from "@testing-library/react";

import { VolatilityPanel } from "@/components/analytics/volatility-panel";
import type { TermStructurePoint, VolSurfacePoint } from "@/lib/types";

const timestamp = "2026-07-31T15:30:00Z";

function skewPoint(strike: number, impliedVol: number, right: "call" | "put"): VolSurfacePoint {
  return {
    symbol: "AAPL",
    expiration: "2026-08-21",
    strike,
    moneyness: strike / 215,
    implied_vol: impliedVol,
    option_right: right,
    updated_at: timestamp,
  };
}

function termPoint(expiration: string, days: number, iv: number | null): TermStructurePoint {
  return {
    symbol: "AAPL",
    expiration,
    days_to_expiry: days,
    atm_iv: iv,
    atm_strike: iv === null ? null : 215,
    method: iv === null ? null : "nearest-strike call/put mean",
    sample_size: iv === null ? 0 : 2,
    status: iv === null ? "unavailable" : "available",
    updated_at: timestamp,
  };
}

test("smile/skew shows an explicit insufficient-data state for fewer than three strikes", () => {
  render(
    <VolatilityPanel
      skew={[skewPoint(210, 0.24, "put"), skewPoint(215, 0.23, "call")]}
      termStructure={[]}
      hasStrategy={false}
    />
  );

  expect(screen.getByText(/Insufficient smile data: 2 valid strikes/)).toBeInTheDocument();
  expect(screen.getByText("Volatility Smile / Skew")).toBeInTheDocument();
});

test("term structure shows unavailable expirations and an explicit sparse state", () => {
  render(
    <VolatilityPanel
      skew={[]}
      termStructure={[termPoint("2026-08-07", 7, 0.23), termPoint("2026-08-14", 14, null)]}
      hasStrategy={false}
    />
  );

  expect(screen.getByText(/Insufficient term data: 1 usable expiration/)).toBeInTheDocument();
  expect(screen.getByText("1 usable / 1 unavailable")).toBeInTheDocument();
});

test("full volatility analytics labels conventional axes and aggregation methods", () => {
  render(
    <VolatilityPanel
      skew={[
        skewPoint(200, 0.29, "put"),
        skewPoint(210, 0.24, "put"),
        skewPoint(215, 0.23, "call"),
        skewPoint(215, 0.25, "put"),
        skewPoint(220, 0.245, "call"),
        skewPoint(230, 0.28, "call"),
      ]}
      termStructure={[
        termPoint("2026-08-07", 7, 0.23),
        termPoint("2026-08-14", 14, 0.24),
        termPoint("2026-08-21", 21, 0.25),
      ]}
      hasStrategy={false}
    />
  );

  expect(screen.getByRole("img", { name: /X-axis: Strike.*Y-axis: Implied volatility/ })).toBeInTheDocument();
  expect(screen.getByRole("img", { name: /X-axis: Days to expiry.*Y-axis: ATM implied volatility/ })).toBeInTheDocument();
  expect(screen.getByText(/OTM composite: puts below spot/)).toBeInTheDocument();
  expect(screen.getByText(/Nearest-strike call\/put mean/)).toBeInTheDocument();
});
