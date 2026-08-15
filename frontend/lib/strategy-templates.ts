import { getStagedOptionEntryPrice } from "@/lib/strategy-pricing";
import type { ChainSnapshot, OptionQuote, OptionRight, StrategyLegDraft } from "@/lib/types";

const NON_STAGEABLE_FLAGS = new Set([
  "crossed_market",
  "market_data_unavailable",
  "subscription_missing",
  "stale",
  "unusable_mark",
]);

function isStageable(quote: OptionQuote) {
  return (
    getStagedOptionEntryPrice(quote) !== undefined &&
    !quote.market_data_unavailable &&
    !quote.subscription_missing &&
    !quote.data_flags.some((flag) => NON_STAGEABLE_FLAGS.has(flag))
  );
}

function optionLeg(quote: OptionQuote, side: "long" | "short", quantity = 1): StrategyLegDraft {
  return {
    leg_id: crypto.randomUUID(),
    instrument_type: "option",
    side,
    quantity,
    contract: quote.contract,
    quote,
    entry_price: getStagedOptionEntryPrice(quote),
  };
}

function stockLeg(symbol: string, price: number, side: "long" | "short", quantity = 100): StrategyLegDraft {
  return {
    leg_id: crypto.randomUUID(),
    instrument_type: "stock",
    side,
    quantity,
    stock_price: price,
    entry_price: price,
    underlying_symbol: symbol,
  };
}

function orderedQuotes(chain: ChainSnapshot, right: OptionRight) {
  return [...(right === "call" ? chain.calls : chain.puts)]
    .filter(isStageable)
    .sort((left, rightQuote) => left.contract.strike - rightQuote.contract.strike);
}

function nearestToSpot(quotes: OptionQuote[], spot: number) {
  return [...quotes].sort(
    (left, right) =>
      Math.abs(left.contract.strike - spot) - Math.abs(right.contract.strike - spot) ||
      left.contract.strike - right.contract.strike
  )[0];
}

function selectedFromChain(chain: ChainSnapshot, selected?: OptionQuote | null) {
  if (!selected || selected.contract.symbol !== chain.symbol) {
    return undefined;
  }
  return [...chain.calls, ...chain.puts].find(
    (quote) => quote.contract.contract_id === selected.contract.contract_id && isStageable(quote)
  );
}

function commonAtmPair(calls: OptionQuote[], puts: OptionQuote[], spot: number) {
  const putsByStrike = new Map(puts.map((quote) => [quote.contract.strike, quote]));
  const call = nearestToSpot(
    calls.filter((quote) => putsByStrike.has(quote.contract.strike)),
    spot
  );
  return call ? ([call, putsByStrike.get(call.contract.strike)!] as const) : undefined;
}

function symmetricCallButterfly(calls: OptionQuote[], spot: number) {
  const candidates: [OptionQuote, OptionQuote, OptionQuote][] = [];
  for (let index = 1; index < calls.length - 1; index += 1) {
    const low = calls[index - 1];
    const middle = calls[index];
    const high = calls[index + 1];
    const lowerWidth = middle.contract.strike - low.contract.strike;
    const upperWidth = high.contract.strike - middle.contract.strike;
    if (Math.abs(lowerWidth - upperWidth) <= 1e-8) {
      candidates.push([low, middle, high]);
    }
  }
  return candidates.sort(
    (left, right) => Math.abs(left[1].contract.strike - spot) - Math.abs(right[1].contract.strike - spot)
  )[0];
}

export function buildTemplate(chain: ChainSnapshot, template: string, selected?: OptionQuote | null): StrategyLegDraft[] {
  const calls = orderedQuotes(chain, "call");
  const puts = orderedQuotes(chain, "put");
  const selectedQuote = selectedFromChain(chain, selected);
  const atmCall = nearestToSpot(calls, chain.underlying.spot);
  const atmPut = nearestToSpot(puts, chain.underlying.spot);
  const selectedCall = selectedQuote?.contract.right === "call" ? selectedQuote : atmCall;
  const selectedPut = selectedQuote?.contract.right === "put" ? selectedQuote : atmPut;
  const otmCalls = calls.filter((quote) => quote.contract.strike > chain.underlying.spot);
  const otmPuts = puts.filter((quote) => quote.contract.strike < chain.underlying.spot);
  const otmCall = otmCalls[0];
  const otmPut = otmPuts.at(-1);

  switch (template) {
    case "long_call":
      return selectedCall ? [optionLeg(selectedCall, "long")] : [];
    case "short_call":
      return selectedCall ? [optionLeg(selectedCall, "short")] : [];
    case "long_put":
      return selectedPut ? [optionLeg(selectedPut, "long")] : [];
    case "short_put":
      return selectedPut ? [optionLeg(selectedPut, "short")] : [];
    case "covered_call": {
      const coveredCall = calls.find((quote) => quote.contract.strike >= chain.underlying.spot);
      return coveredCall
        ? [stockLeg(chain.symbol, chain.underlying.spot, "long"), optionLeg(coveredCall, "short")]
        : [];
    }
    case "cash_secured_put":
      return otmPut ? [optionLeg(otmPut, "short")] : [];
    case "vertical_spread": {
      const anchor = selectedQuote ?? atmCall;
      if (!anchor) return [];
      const collection = anchor.contract.right === "call" ? calls : puts;
      const anchorIndex = collection.findIndex(
        (quote) => quote.contract.contract_id === anchor.contract.contract_id
      );
      const wing = anchor.contract.right === "call" ? collection[anchorIndex + 1] : collection[anchorIndex - 1];
      return wing ? [optionLeg(anchor, "long"), optionLeg(wing, "short")] : [];
    }
    case "straddle": {
      const pair = commonAtmPair(calls, puts, chain.underlying.spot);
      return pair ? [optionLeg(pair[0], "long"), optionLeg(pair[1], "long")] : [];
    }
    case "strangle":
      return otmCall && otmPut ? [optionLeg(otmCall, "long"), optionLeg(otmPut, "long")] : [];
    case "iron_condor": {
      const longPut = otmPuts.at(-2);
      const shortPut = otmPuts.at(-1);
      const shortCall = otmCalls[0];
      const longCall = otmCalls[1];
      return longPut && shortPut && shortCall && longCall
        ? [
            optionLeg(longPut, "long"),
            optionLeg(shortPut, "short"),
            optionLeg(shortCall, "short"),
            optionLeg(longCall, "long"),
          ]
        : [];
    }
    case "butterfly": {
      const butterfly = symmetricCallButterfly(calls, chain.underlying.spot);
      return butterfly
        ? [
            optionLeg(butterfly[0], "long"),
            optionLeg(butterfly[1], "short", 2),
            optionLeg(butterfly[2], "long"),
          ]
        : [];
    }
    default:
      return [];
  }
}
