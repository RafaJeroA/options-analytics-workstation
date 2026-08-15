import type { MarketDataMode, PayoffMetricState, QuoteSource } from "@/lib/types";

export function isFiniteNumber(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value);
}

export function formatPrice(value: number | null | undefined) {
  if (!isFiniteNumber(value)) {
    return "--";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: value >= 100 ? 2 : 2,
    maximumFractionDigits: 2,
  }).format(value);
}

export function formatPercent(value: number | null | undefined, digits = 2) {
  if (!isFiniteNumber(value)) {
    return "--";
  }
  return `${(value * 100).toFixed(digits)}%`;
}

export function formatSignedPercent(value: number | null | undefined, digits = 2) {
  if (!isFiniteNumber(value)) {
    return "--";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}%`;
}

export function formatSignedNumber(value: number | null | undefined, digits = 2) {
  if (!isFiniteNumber(value)) {
    return "--";
  }
  return `${value >= 0 ? "+" : ""}${value.toFixed(digits)}`;
}

export function formatNumber(value: number | null | undefined, digits = 2) {
  return isFiniteNumber(value) ? value.toFixed(digits) : "--";
}

export function formatPayoffMetric(
  value: number | null | undefined,
  state: PayoffMetricState | undefined
) {
  if (state === "unlimited") {
    return "Unlimited";
  }
  if (state === "finite" && isFiniteNumber(value)) {
    return formatPrice(value);
  }
  return "Unavailable";
}

export function formatMarketDataMode(mode: MarketDataMode | undefined) {
  const labels: Record<MarketDataMode, string> = {
    mock: "Mock / synthetic",
    unconfirmed: "IBKR · UNCONFIRMED",
    live: "IBKR · LIVE",
    frozen: "IBKR · FROZEN",
    delayed: "IBKR · DELAYED",
    delayed_frozen: "IBKR · DELAYED FROZEN",
  };
  return mode ? labels[mode] : "Loading";
}

export function formatQuoteSource(source: QuoteSource | undefined) {
  const labels: Record<QuoteSource, string> = {
    mock: "Mock / synthetic",
    broker: "Broker quote",
    broker_model: "Broker model",
    local_model: "Local model",
  };
  return source ? labels[source] : "Unavailable";
}
