import { isFiniteNumber } from "@/lib/format";
import type { TermStructurePoint, VolSurfacePoint } from "@/lib/types";

const ATM_MONEYNESS_TOLERANCE = 0.005;

export interface SmileChartPoint {
  strike: number;
  moneyness: number;
  iv: number;
  expiration: string;
  optionRight: "call" | "put" | "call + put";
  method: string;
}

export interface TermChartPoint {
  expiration: string;
  days: number;
  iv: number;
  atmStrike: number;
  method: string;
  sampleSize: number;
}

function mean(values: number[]) {
  return values.reduce((total, value) => total + value, 0) / values.length;
}

export function prepareSmileChartData(points: VolSurfacePoint[]): SmileChartPoint[] {
  const byStrike = new Map<number, VolSurfacePoint[]>();
  for (const point of points) {
    if (
      !isFiniteNumber(point.strike) ||
      !isFiniteNumber(point.moneyness) ||
      !isFiniteNumber(point.implied_vol) ||
      point.strike <= 0 ||
      point.moneyness <= 0 ||
      point.implied_vol <= 0
    ) {
      continue;
    }
    const existing = byStrike.get(point.strike) ?? [];
    existing.push(point);
    byStrike.set(point.strike, existing);
  }

  return [...byStrike.entries()]
    .sort(([left], [right]) => left - right)
    .flatMap(([strike, candidates]) => {
      const moneyness = mean(candidates.map((point) => point.moneyness));
      const nearAtm = Math.abs(moneyness - 1) <= ATM_MONEYNESS_TOLERANCE;
      const preferredRight = moneyness < 1 ? "put" : "call";
      const selected = nearAtm
        ? candidates
        : candidates.filter((point) => point.option_right === preferredRight);
      if (!selected.length) {
        return [];
      }
      const rights = [...new Set(selected.map((point) => point.option_right))].sort();
      const optionRight = rights.length > 1 ? "call + put" : rights[0]!;
      return [
        {
          strike,
          moneyness,
          iv: mean(selected.map((point) => point.implied_vol)) * 100,
          expiration: [...selected].sort((left, right) =>
            left.expiration.localeCompare(right.expiration)
          )[0]!.expiration,
          optionRight,
          method: nearAtm ? "ATM call/put mean" : `OTM ${optionRight}`,
        } satisfies SmileChartPoint,
      ];
    });
}

export function prepareTermChartData(points: TermStructurePoint[]): TermChartPoint[] {
  const byExpiration = new Map<string, TermStructurePoint[]>();
  for (const point of points) {
    const timestamp = Date.parse(`${point.expiration}T00:00:00Z`);
    if (
      point.status !== "available" ||
      !Number.isFinite(timestamp) ||
      !isFiniteNumber(point.days_to_expiry) ||
      !isFiniteNumber(point.atm_iv) ||
      !isFiniteNumber(point.atm_strike) ||
      point.days_to_expiry < 0 ||
      point.atm_iv <= 0 ||
      point.atm_strike <= 0
    ) {
      continue;
    }
    const existing = byExpiration.get(point.expiration) ?? [];
    existing.push(point);
    byExpiration.set(point.expiration, existing);
  }

  return [...byExpiration.entries()]
    .sort(([left], [right]) => left.localeCompare(right))
    .map(([expiration, candidates]) => ({
      expiration,
      days: Math.min(...candidates.map((point) => point.days_to_expiry)),
      iv: mean(candidates.map((point) => point.atm_iv as number)) * 100,
      atmStrike: mean(candidates.map((point) => point.atm_strike as number)),
      method: candidates.find((point) => point.method)?.method ?? "nearest-strike representative IV",
      sampleSize: Math.max(...candidates.map((point) => point.sample_size)),
    }));
}

export function paddedNumericDomain(
  values: number[],
  { minimum = 0, minimumSpan, paddingRatio = 0.12 }: { minimum?: number; minimumSpan: number; paddingRatio?: number }
): [number, number] {
  const finiteValues = values.filter(isFiniteNumber);
  if (!finiteValues.length) {
    return [minimum, minimum + minimumSpan];
  }
  const rawMinimum = Math.min(...finiteValues);
  const rawMaximum = Math.max(...finiteValues);
  const center = (rawMinimum + rawMaximum) / 2;
  const span = Math.max(rawMaximum - rawMinimum, minimumSpan);
  const padding = span * paddingRatio;
  return [Math.max(minimum, center - span / 2 - padding), center + span / 2 + padding];
}
