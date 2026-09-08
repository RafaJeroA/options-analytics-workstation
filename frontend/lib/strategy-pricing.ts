import type { OptionQuote, StrategyDefinition, StrategyValuation } from "@/lib/types";

export const MIXED_EXPIRATION_PAYOFF_REASON =
  "Exact single-spot expiry payoff, global bounds, and breakevens are unavailable for multiple option expirations because settlement spots can differ.";

const NON_STAGEABLE_FLAGS = new Set([
  "crossed_market",
  "market_data_unavailable",
  "subscription_missing",
  "stale",
  "unusable_mark",
]);

export function getStagedOptionEntryPrice(quote?: OptionQuote | null): number | undefined {
  if (!quote) {
    return undefined;
  }

  if (
    quote.market_data_unavailable ||
    quote.subscription_missing ||
    quote.data_flags.some((flag) => NON_STAGEABLE_FLAGS.has(flag))
  ) {
    return undefined;
  }

  for (const candidate of [quote.mark, quote.last]) {
    if (candidate !== null && candidate !== undefined && Number.isFinite(candidate) && candidate > 0) {
      return candidate;
    }
  }

  return undefined;
}

export function hasMultipleOptionExpirations(strategy: StrategyDefinition) {
  const expirations = new Set(
    strategy.legs
      .filter((leg) => leg.instrument_type === "option" && leg.contract?.expiration)
      .map((leg) => leg.contract!.expiration)
  );
  return expirations.size > 1;
}

export function payoffExplanation(valuation?: StrategyValuation, fallback?: string) {
  const messages = [valuation?.status_message, valuation?.payoff_unavailable_reason, fallback].filter(
    (message): message is string => Boolean(message)
  );
  return [...new Set(messages)].join(" ") || undefined;
}

export function payoffMetricsAvailable(valuation?: StrategyValuation) {
  return Boolean(
    valuation &&
      (valuation.max_profit_state !== "unavailable" ||
        valuation.max_loss_state !== "unavailable" ||
        valuation.payoff.length)
  );
}
