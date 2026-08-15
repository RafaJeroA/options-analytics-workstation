import { describe, expect, test } from "vitest";

import {
  paddedNumericDomain,
  prepareSmileChartData,
  prepareTermChartData,
} from "@/lib/analytics-chart-data";
import type { TermStructurePoint, VolSurfacePoint } from "@/lib/types";

const timestamp = "2026-07-31T15:30:00Z";

function skewPoint(
  strike: number,
  impliedVol: number,
  right: "call" | "put",
  moneyness = strike / 215
): VolSurfacePoint {
  return {
    symbol: "AAPL",
    expiration: "2026-08-21",
    strike,
    moneyness,
    implied_vol: impliedVol,
    option_right: right,
    updated_at: timestamp,
  };
}

function termPoint(
  expiration: string,
  days: number,
  iv: number | null,
  status: "available" | "unavailable" = iv === null ? "unavailable" : "available"
): TermStructurePoint {
  return {
    symbol: "AAPL",
    expiration,
    days_to_expiry: days,
    atm_iv: iv,
    atm_strike: iv === null ? null : 215,
    method: iv === null ? null : "nearest-strike call/put mean",
    sample_size: iv === null ? 0 : 2,
    status,
    updated_at: timestamp,
  };
}

describe("prepareSmileChartData", () => {
  test("sorts strikes and uses a conventional OTM composite", () => {
    const data = prepareSmileChartData([
      skewPoint(225, 0.26, "put"),
      skewPoint(205, 0.25, "put"),
      skewPoint(225, 0.24, "call"),
      skewPoint(205, 0.80, "call"),
      skewPoint(215, 0.22, "call", 1),
      skewPoint(215, 0.24, "put", 1),
    ]);

    expect(data.map((point) => point.strike)).toEqual([205, 215, 225]);
    expect(data.map((point) => point.iv)).toEqual([25, 23, 24]);
    expect(data.map((point) => point.optionRight)).toEqual(["put", "call + put", "call"]);
  });

  test("deduplicates same-right strikes deterministically by averaging", () => {
    const points = [skewPoint(225, 0.25, "call"), skewPoint(225, 0.27, "call")];

    expect(prepareSmileChartData(points)).toEqual([
      expect.objectContaining({ strike: 225, iv: 26, optionRight: "call" }),
    ]);
    expect(prepareSmileChartData(points.reverse())).toEqual(
      prepareSmileChartData([...points].reverse())
    );
  });

  test("excludes missing and non-finite IV without converting values to zero", () => {
    const data = prepareSmileChartData([
      skewPoint(205, Number.NaN, "put"),
      skewPoint(210, Number.POSITIVE_INFINITY, "put"),
      skewPoint(215, 0 as number, "call"),
      skewPoint(220, 0.24, "call"),
    ]);

    expect(data).toHaveLength(1);
    expect(data[0]).toEqual(expect.objectContaining({ strike: 220, iv: 24 }));
    expect(JSON.stringify(data)).not.toMatch(/NaN|Infinity/);
  });

  test("preserves finite extreme values while returning a padded unclipped domain", () => {
    const data = prepareSmileChartData([
      skewPoint(205, 0.15, "put"),
      skewPoint(215, 0.25, "call", 1),
      skewPoint(225, 2.5, "call"),
    ]);
    const domain = paddedNumericDomain(data.map((point) => point.iv), { minimumSpan: 8 });

    expect(data.map((point) => point.iv)).toEqual([15, 25, 250]);
    expect(domain[0]).toBeLessThan(15);
    expect(domain[1]).toBeGreaterThan(250);
  });
});

describe("prepareTermChartData", () => {
  test("orders expirations chronologically and excludes explicitly unavailable rows", () => {
    const data = prepareTermChartData([
      termPoint("2026-09-04", 35, 0.26),
      termPoint("2026-08-14", 14, null),
      termPoint("2026-08-07", 7, 0.23),
      termPoint("2026-08-21", 21, 0.25),
    ]);

    expect(data.map((point) => point.expiration)).toEqual([
      "2026-08-07",
      "2026-08-21",
      "2026-09-04",
    ]);
    expect(data.every((point) => Number.isFinite(point.iv))).toBe(true);
  });

  test("handles partial data and deduplicates an expiration", () => {
    const data = prepareTermChartData([
      termPoint("2026-08-07", 7, 0.22),
      { ...termPoint("2026-08-07", 7, 0.24), sample_size: 1 },
      termPoint("not-a-date", 14, 0.25),
      termPoint("2026-08-21", 21, Number.POSITIVE_INFINITY),
    ]);

    expect(data).toEqual([
      expect.objectContaining({ expiration: "2026-08-07", days: 7, iv: 23, sampleSize: 2 }),
    ]);
    expect(JSON.stringify(data)).not.toMatch(/NaN|Infinity/);
  });

  test("returns finite one-point and two-point datasets for explicit sparse rendering", () => {
    const onePoint = prepareTermChartData([termPoint("2026-08-07", 7, 0.23)]);
    const twoPoints = prepareTermChartData([
      termPoint("2026-08-07", 7, 0.23),
      termPoint("2026-08-14", 14, 0.24),
    ]);

    expect(onePoint).toHaveLength(1);
    expect(twoPoints).toHaveLength(2);
    expect(twoPoints.flatMap((point) => [point.days, point.iv, point.atmStrike]).every(Number.isFinite)).toBe(
      true
    );
  });
});
