import type { ChainSnapshot, DataQualityFlag, OptionQuote } from "@/lib/types";

export interface ChainFilters {
  maxAbsMoneynessPct: number;
  deltaMin: number;
  deltaMax: number;
  ivMin: number;
  ivMax: number;
  minVolume: number;
  minOpenInterest: number;
  maxSpreadPct: number;
  sortBy: "strike" | "callIv" | "putIv" | "callDelta" | "putDelta";
  sortDirection: "asc" | "desc";
}

export interface ChainRow {
  strike: number;
  call?: OptionQuote;
  put?: OptionQuote;
  pinned: boolean;
  flags: DataQualityFlag[];
}

export const defaultChainFilters: ChainFilters = {
  maxAbsMoneynessPct: 20,
  deltaMin: -1,
  deltaMax: 1,
  ivMin: 0,
  ivMax: 3,
  minVolume: 0,
  minOpenInterest: 0,
  maxSpreadPct: 0.2,
  sortBy: "strike",
  sortDirection: "asc",
};

function getOpenInterest(quote?: OptionQuote) {
  return quote?.open_interest ?? quote?.openInterest ?? 0;
}

export function getSpreadPct(quote?: OptionQuote) {
  if (!quote) {
    return Infinity;
  }

  const bid = quote.bid;
  const ask = quote.ask;
  if (bid === null || bid === undefined || ask === null || ask === undefined) {
    return Infinity;
  }
  if (bid <= 0 || ask <= 0 || ask < bid) {
    return Infinity;
  }

  const mid = quote.mark ?? (bid + ask) / 2;
  if (!Number.isFinite(mid) || mid <= 0) {
    return Infinity;
  }
  return (ask - bid) / mid;
}

function rowFlags(call?: OptionQuote, put?: OptionQuote) {
  return [...(call?.data_flags ?? []), ...(put?.data_flags ?? [])];
}

function passesScalarFilter(value: number | null | undefined, minimum: number, maximum?: number, fallback = 0) {
  const candidate = value ?? fallback;
  if (candidate < minimum) {
    return false;
  }
  if (maximum !== undefined && candidate > maximum) {
    return false;
  }
  return true;
}

function passesOptionalRange(
  value: number | null | undefined,
  minimum: number,
  maximum: number,
  defaultMinimum: number,
  defaultMaximum: number
) {
  if (value === null || value === undefined) {
    return minimum === defaultMinimum && maximum === defaultMaximum;
  }
  return value >= minimum && value <= maximum;
}

function filterSide(quote: OptionQuote | undefined, filters: ChainFilters) {
  if (!quote) {
    return undefined;
  }

  const spreadPct = getSpreadPct(quote);
  if (spreadPct > filters.maxSpreadPct) {
    return undefined;
  }
  if (!passesScalarFilter(quote.volume, filters.minVolume)) {
    return undefined;
  }
  if (!passesScalarFilter(getOpenInterest(quote), filters.minOpenInterest)) {
    return undefined;
  }
  if (
    !passesOptionalRange(
      quote.implied_vol,
      filters.ivMin,
      filters.ivMax,
      defaultChainFilters.ivMin,
      defaultChainFilters.ivMax
    )
  ) {
    return undefined;
  }
  if (
    !passesOptionalRange(
      quote.greeks?.delta,
      filters.deltaMin,
      filters.deltaMax,
      defaultChainFilters.deltaMin,
      defaultChainFilters.deltaMax
    )
  ) {
    return undefined;
  }
  return quote;
}

function compareMaybeNumber(left: number | null | undefined, right: number | null | undefined, direction: "asc" | "desc") {
  const leftMissing = left === null || left === undefined || Number.isNaN(left);
  const rightMissing = right === null || right === undefined || Number.isNaN(right);
  if (leftMissing && rightMissing) {
    return 0;
  }
  if (leftMissing) {
    return 1;
  }
  if (rightMissing) {
    return -1;
  }
  return direction === "asc" ? left - right : right - left;
}

export function buildChainRows(
  chain: ChainSnapshot | undefined,
  filters: ChainFilters,
  pinnedContracts: string[]
) {
  if (!chain) {
    return [];
  }

  const byStrike = new Map<number, { strike: number; call?: OptionQuote; put?: OptionQuote }>();
  for (const quote of chain.calls) {
    const row = byStrike.get(quote.contract.strike) ?? { strike: quote.contract.strike };
    row.call = quote;
    byStrike.set(quote.contract.strike, row);
  }
  for (const quote of chain.puts) {
    const row = byStrike.get(quote.contract.strike) ?? { strike: quote.contract.strike };
    row.put = quote;
    byStrike.set(quote.contract.strike, row);
  }

  const rows = [...byStrike.values()]
    .map((row) => {
      const filteredCall = filterSide(row.call, filters);
      const filteredPut = filterSide(row.put, filters);
      return {
        strike: row.strike,
        call: filteredCall,
        put: filteredPut,
        pinned:
          pinnedContracts.includes(row.call?.contract.contract_id ?? "") ||
          pinnedContracts.includes(row.put?.contract.contract_id ?? ""),
        flags: rowFlags(row.call, row.put),
      };
    })
    .filter((row) => {
      const moneynessPct = Math.abs((row.strike - chain.underlying.spot) / chain.underlying.spot) * 100;
      if (moneynessPct > filters.maxAbsMoneynessPct) {
        return false;
      }
      return Boolean(row.call || row.put);
    });

  rows.sort((left, right) => {
    if (left.pinned !== right.pinned) {
      return left.pinned ? -1 : 1;
    }

    switch (filters.sortBy) {
      case "callIv":
        return compareMaybeNumber(left.call?.implied_vol, right.call?.implied_vol, filters.sortDirection);
      case "putIv":
        return compareMaybeNumber(left.put?.implied_vol, right.put?.implied_vol, filters.sortDirection);
      case "callDelta":
        return compareMaybeNumber(left.call?.greeks?.delta, right.call?.greeks?.delta, filters.sortDirection);
      case "putDelta":
        return compareMaybeNumber(left.put?.greeks?.delta, right.put?.greeks?.delta, filters.sortDirection);
      default:
        return filters.sortDirection === "asc" ? left.strike - right.strike : right.strike - left.strike;
    }
  });

  return rows;
}
