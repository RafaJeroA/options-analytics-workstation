import type { OptionQuote, StrategyValuation } from "@/lib/types";

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

export function payoffMetricsAvailable(valuation?: StrategyValuation) {
  return Boolean(
    valuation &&
      (valuation.max_profit_state !== "unavailable" ||
        valuation.max_loss_state !== "unavailable" ||
        valuation.payoff.length)
  );
}
