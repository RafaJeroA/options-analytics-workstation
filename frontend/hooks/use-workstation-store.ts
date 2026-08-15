"use client";

import { create } from "zustand";
import { persist } from "zustand/middleware";

import { defaultChainFilters, type ChainFilters } from "@/lib/chain";
import type { ChainSnapshot, OptionQuote, PricingAssumptions, StrategyDefinition, StrategyLegDraft } from "@/lib/types";

interface WorkstationState {
  symbol: string;
  selectedExpiration?: string;
  selectedContract?: OptionQuote;
  activeView: "chain" | "strategy" | "analytics";
  watchlistSymbols: string[];
  pinnedContracts: string[];
  strategy: StrategyDefinition;
  assumptions: PricingAssumptions;
  filters: ChainFilters;
  setSymbol: (symbol: string) => void;
  setSelectedExpiration: (expiration?: string) => void;
  setSelectedContract: (quote?: OptionQuote) => void;
  setActiveView: (view: WorkstationState["activeView"]) => void;
  setWatchlistSymbols: (symbols: string[]) => void;
  togglePinnedContract: (contractId: string) => void;
  addStrategyLeg: (leg: StrategyLegDraft) => void;
  replaceStrategy: (name: string, legs: StrategyLegDraft[]) => void;
  removeStrategyLeg: (legId: string) => void;
  clearStrategy: () => void;
  updateAssumptions: (partial: Partial<PricingAssumptions>) => void;
  updateFilters: (partial: Partial<ChainFilters>) => void;
  syncUnderlying: (symbol: string, price: number) => void;
  reconcileChainSelection: (chain: ChainSnapshot) => void;
}

const baseAssumptions: PricingAssumptions = {
  underlying_price: 0,
  risk_free_rate: 0.0425,
  dividend_yield: 0,
  volatility_shift: 0,
  days_forward: 0,
};

function emptyStrategy(symbol: string, underlyingPrice = 0): StrategyDefinition {
  return {
    name: "Custom Strategy",
    underlying_symbol: symbol,
    underlying_price: underlyingPrice,
    legs: [],
  };
}

function strategyMatchesSymbol(strategy: StrategyDefinition, symbol: string) {
  const upper = symbol.toUpperCase();
  if (strategy.underlying_symbol.toUpperCase() !== upper) {
    return false;
  }

  return strategy.legs.every((leg) => {
    if (leg.instrument_type === "option") {
      return Boolean(leg.contract && leg.contract.symbol.toUpperCase() === upper);
    }
    return Boolean(leg.underlying_symbol && leg.underlying_symbol.toUpperCase() === upper);
  });
}

function sameStringArray(left: string[], right: string[]) {
  return left.length === right.length && left.every((value, index) => value === right[index]);
}

function chainContractsById(chain: ChainSnapshot) {
  const contracts = new Map<string, OptionQuote>();
  for (const quote of chain.calls) {
    contracts.set(quote.contract.contract_id, quote);
  }
  for (const quote of chain.puts) {
    contracts.set(quote.contract.contract_id, quote);
  }
  return contracts;
}

export const useWorkstationStore = create<WorkstationState>()(
  persist(
    (set) => ({
      symbol: "SPY",
      activeView: "chain",
      watchlistSymbols: ["SPY", "AAPL", "QQQ"],
      pinnedContracts: [],
      strategy: emptyStrategy("SPY"),
      assumptions: baseAssumptions,
      filters: defaultChainFilters,
      setSymbol: (symbol) =>
        set((state) => {
          const upper = symbol.toUpperCase();
          if (state.symbol === upper) {
            return state;
          }
          return {
            symbol: upper,
            selectedExpiration: undefined,
            selectedContract: undefined,
            strategy: emptyStrategy(upper),
            assumptions: {
              ...state.assumptions,
              underlying_price: 0,
            },
          };
        }),
      setSelectedExpiration: (selectedExpiration) =>
        set((state) => (state.selectedExpiration === selectedExpiration ? state : { selectedExpiration })),
      setSelectedContract: (selectedContract) =>
        set((state) =>
          state.selectedContract?.contract.contract_id === selectedContract?.contract.contract_id
            ? state
            : { selectedContract }
        ),
      setActiveView: (activeView) => set((state) => (state.activeView === activeView ? state : { activeView })),
      setWatchlistSymbols: (watchlistSymbols) =>
        set((state) => (sameStringArray(state.watchlistSymbols, watchlistSymbols) ? state : { watchlistSymbols })),
      togglePinnedContract: (contractId) =>
        set((state) => ({
          pinnedContracts: state.pinnedContracts.includes(contractId)
            ? state.pinnedContracts.filter((item) => item !== contractId)
            : [...state.pinnedContracts, contractId],
        })),
      addStrategyLeg: (leg) =>
        set((state) => {
          const candidate = { ...state.strategy, legs: [...state.strategy.legs, leg] };
          if (!strategyMatchesSymbol(candidate, state.symbol)) {
            return state;
          }
          return {
            activeView: "strategy",
            strategy: candidate,
          };
        }),
      replaceStrategy: (name, legs) =>
        set((state) => {
          const candidate = { ...state.strategy, name, legs };
          if (!strategyMatchesSymbol(candidate, state.symbol)) {
            return state;
          }
          return {
            activeView: "strategy",
            strategy: candidate,
          };
        }),
      removeStrategyLeg: (legId) =>
        set((state) => ({
          strategy: {
            ...state.strategy,
            legs: state.strategy.legs.filter((leg) => leg.leg_id !== legId),
          },
        })),
      clearStrategy: () =>
        set((state) => ({
          strategy: {
            ...state.strategy,
            name: "Custom Strategy",
            legs: [],
          },
        })),
      updateAssumptions: (partial) =>
        set((state) => {
          const nextAssumptions = {
            ...state.assumptions,
            ...partial,
          };
          const changed = Object.entries(partial).some(
            ([key, value]) => state.assumptions[key as keyof PricingAssumptions] !== value
          );
          return changed ? { assumptions: nextAssumptions } : state;
        }),
      updateFilters: (partial) =>
        set((state) => {
          const nextFilters = {
            ...state.filters,
            ...partial,
          };
          const changed = Object.entries(partial).some(
            ([key, value]) => state.filters[key as keyof ChainFilters] !== value
          );
          return changed ? { filters: nextFilters } : state;
        }),
      syncUnderlying: (symbol, price) =>
        set((state) => {
          const upper = symbol.toUpperCase();
          const symbolChanged = state.symbol !== upper;
          if (
            state.symbol === upper &&
            state.assumptions.underlying_price === price &&
            state.strategy.underlying_symbol === upper &&
            state.strategy.underlying_price === price
          ) {
            return state;
          }
          return {
            symbol: upper,
            selectedExpiration: symbolChanged ? undefined : state.selectedExpiration,
            selectedContract: symbolChanged ? undefined : state.selectedContract,
            assumptions: {
              ...state.assumptions,
              underlying_price: price,
            },
            strategy:
              symbolChanged || !strategyMatchesSymbol(state.strategy, upper)
                ? emptyStrategy(upper, price)
                : {
                    ...state.strategy,
                    underlying_price: price,
                  },
          };
        }),
      reconcileChainSelection: (chain) =>
        set((state) => {
          if (state.symbol !== chain.symbol) {
            return state;
          }

          const contracts = chainContractsById(chain);
          const selectedContractId = state.selectedContract?.contract.contract_id;
          const nextSelectedContract = selectedContractId ? contracts.get(selectedContractId) : undefined;
          const selectedExpiration = chain.selected_expiration;

          if (
            state.selectedExpiration === selectedExpiration &&
            state.selectedContract === nextSelectedContract
          ) {
            return state;
          }

          return {
            selectedExpiration,
            selectedContract: nextSelectedContract,
          };
        }),
    }),
    {
      name: "modellator-workstation",
      partialize: (state) => ({
        symbol: state.symbol,
        selectedExpiration: state.selectedExpiration,
        activeView: state.activeView,
        watchlistSymbols: state.watchlistSymbols,
        pinnedContracts: state.pinnedContracts,
        strategy: state.strategy,
        assumptions: state.assumptions,
        filters: state.filters,
      }),
      merge: (persistedState, currentState) => {
        const persisted = persistedState as Partial<WorkstationState>;
        const merged = { ...currentState, ...persisted };
        const symbol = merged.symbol.toUpperCase();
        return {
          ...merged,
          symbol,
          strategy: strategyMatchesSymbol(merged.strategy, symbol)
            ? merged.strategy
            : emptyStrategy(symbol, merged.assumptions.underlying_price),
        };
      },
    }
  )
);
