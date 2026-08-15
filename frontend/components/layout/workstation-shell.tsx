"use client";

import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BarChart3, BriefcaseBusiness, Clock3, Waves } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Group as PanelGroup, Panel, Separator as PanelResizeHandle } from "react-resizable-panels";

import { VolatilityPanel } from "@/components/analytics/volatility-panel";
import { ChainExplorer } from "@/components/chain/chain-explorer";
import { Sidebar } from "@/components/layout/sidebar";
import { RightPanel } from "@/components/layout/right-panel";
import { StrategyBuilder } from "@/components/strategy/strategy-builder";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { useMarketStreams } from "@/hooks/use-market-streams";
import { useWorkstationStore } from "@/hooks/use-workstation-store";
import { api, apiErrorLabel, apiErrorMessage, isRetryableApiError } from "@/lib/api";
import { formatMarketDataMode, formatPrice, formatSignedPercent, isFiniteNumber } from "@/lib/format";
import { getStagedOptionEntryPrice } from "@/lib/strategy-pricing";
import { buildTemplate } from "@/lib/strategy-templates";

export function WorkstationShell() {
  const queryClient = useQueryClient();
  const [activeSavedStrategyId, setActiveSavedStrategyId] = useState<string>();
  const {
    symbol,
    selectedExpiration,
    selectedContract,
    activeView,
    watchlistSymbols,
    strategy,
    assumptions,
    pinnedContracts,
    filters,
    setSymbol,
    setSelectedExpiration,
    setSelectedContract,
    setActiveView,
    setWatchlistSymbols,
    addStrategyLeg,
    replaceStrategy,
    updateAssumptions,
    updateFilters,
    togglePinnedContract,
    removeStrategyLeg,
    clearStrategy,
    syncUnderlying,
    reconcileChainSelection,
  } = useWorkstationStore();

  const summaryQuery = useQuery({
    queryKey: ["summary", symbol],
    queryFn: () => api.getUnderlyingSummary(symbol),
    staleTime: 45_000,
    retry: 0,
  });

  const chainQuery = useQuery({
    queryKey: ["chain", symbol, selectedExpiration],
    queryFn: () => api.getChain(symbol, selectedExpiration),
    enabled: summaryQuery.isSuccess || summaryQuery.isError,
    staleTime: 20_000,
    retry: 0,
  });

  const watchlistQuery = useQuery({
    queryKey: ["watchlist"],
    queryFn: () => api.getWatchlist(),
    staleTime: 300_000,
  });

  const savedStrategiesQuery = useQuery({
    queryKey: ["saved-strategies"],
    queryFn: () => api.getSavedStrategies(),
    staleTime: 5_000,
    retry: 0,
  });

  const activeChain = chainQuery.data;
  const activeSelectedExpiration = activeChain?.selected_expiration ?? selectedExpiration;
  const activeSelectedContract = useMemo(() => {
    if (!selectedContract) {
      return undefined;
    }
    if (!activeChain) {
      return selectedContract;
    }
    return [...activeChain.calls, ...activeChain.puts].find(
      (quote) => quote.contract.contract_id === selectedContract.contract.contract_id
    );
  }, [activeChain, selectedContract]);

  const activeSummary = summaryQuery.data ?? activeChain?.underlying;
  const activeUnderlyingPrice =
    activeSummary?.spot ??
    assumptions.underlying_price;
  const hasActiveUnderlyingPrice = isFiniteNumber(activeUnderlyingPrice) && activeUnderlyingPrice > 0;
  const hasStagedStrategy = strategy.legs.length > 0;
  const valuationDate = (activeChain?.updated_at ?? activeSummary?.timestamp)?.slice(0, 10);
  const pricedStrategy = useMemo(
    () => ({
      ...strategy,
      underlying_symbol: symbol,
      underlying_price: activeUnderlyingPrice,
    }),
    [activeUnderlyingPrice, strategy, symbol]
  );
  const pricingAssumptions = useMemo(
    () => ({
      ...assumptions,
      valuation_date: valuationDate,
      underlying_price: activeUnderlyingPrice,
    }),
    [activeUnderlyingPrice, assumptions, valuationDate]
  );
  const debouncedPricedStrategy = useDebouncedValue(pricedStrategy, 120);
  const debouncedPricingAssumptions = useDebouncedValue(pricingAssumptions, 250);
  const analyticsEnabled = activeView === "analytics";
  const pricingReady = hasStagedStrategy && hasActiveUnderlyingPrice;
  const debouncedPricingReady =
    pricingReady &&
    debouncedPricedStrategy.legs.length > 0 &&
    isFiniteNumber(debouncedPricedStrategy.underlying_price) &&
    debouncedPricedStrategy.underlying_price > 0 &&
    isFiniteNumber(debouncedPricingAssumptions.underlying_price) &&
    debouncedPricingAssumptions.underlying_price > 0;
  const strategyValuationKey = useMemo(
    () => JSON.stringify({ strategy: debouncedPricedStrategy, assumptions: debouncedPricingAssumptions }),
    [debouncedPricedStrategy, debouncedPricingAssumptions]
  );
  const scenarioInput = useMemo(
    () => ({
      underlying_moves_pct: [-0.2, -0.1, -0.05, 0, 0.05, 0.1, 0.2],
      implied_vol_shifts: [-0.1, -0.05, 0, 0.05, 0.1],
      days_forward: [
        debouncedPricingAssumptions.days_forward,
        debouncedPricingAssumptions.days_forward + 7,
        debouncedPricingAssumptions.days_forward + 14,
        debouncedPricingAssumptions.days_forward + 30,
      ],
      valuation_date: debouncedPricingAssumptions.valuation_date,
      risk_free_rate: debouncedPricingAssumptions.risk_free_rate,
      dividend_yield: debouncedPricingAssumptions.dividend_yield,
    }),
    [
      debouncedPricingAssumptions.days_forward,
      debouncedPricingAssumptions.dividend_yield,
      debouncedPricingAssumptions.risk_free_rate,
      debouncedPricingAssumptions.valuation_date,
    ]
  );
  const scenarioGridKey = useMemo(
    () => JSON.stringify({ strategy: debouncedPricedStrategy, scenario: scenarioInput }),
    [debouncedPricedStrategy, scenarioInput]
  );

  const skewQuery = useQuery({
    queryKey: ["skew", symbol, activeSelectedExpiration],
    queryFn: () => api.getVolSkew(symbol, activeSelectedExpiration),
    enabled: analyticsEnabled && Boolean(activeChain),
    staleTime: 30_000,
    retry: 0,
  });

  const termStructureQuery = useQuery({
    queryKey: ["term-structure", symbol],
    queryFn: () => api.getTermStructure(symbol),
    enabled: analyticsEnabled && (summaryQuery.isSuccess || Boolean(activeChain)),
    staleTime: 30_000,
    retry: 0,
  });

  const strategyValuationQuery = useQuery({
    queryKey: ["strategy-valuation", strategyValuationKey],
    queryFn: () => api.priceStrategy(debouncedPricedStrategy, debouncedPricingAssumptions),
    enabled: debouncedPricingReady,
    staleTime: 2_000,
    retry: 0,
    placeholderData: keepPreviousData,
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
  });
  const pricingLoading =
    (hasStagedStrategy && !debouncedPricingReady) ||
    strategyValuationQuery.isLoading ||
    strategyValuationQuery.isFetching;

  const scenarioGridQuery = useQuery({
    queryKey: ["scenario-grid", scenarioGridKey],
    queryFn: () => api.scenarioGrid(debouncedPricedStrategy, scenarioInput),
    enabled: analyticsEnabled && debouncedPricingReady,
    staleTime: 8_000,
    retry: 0,
    placeholderData: keepPreviousData,
    refetchOnMount: false,
    refetchOnReconnect: false,
    refetchOnWindowFocus: false,
  });

  const addWatchlistMutation = useMutation({
    mutationFn: (watchSymbol: string) => api.addWatchlist(watchSymbol),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["watchlist"] });
    },
  });

  const saveStrategyMutation = useMutation({
    mutationFn: () =>
      api.saveStrategyDefinition(pricedStrategy, strategy.name, activeSavedStrategyId),
    onSuccess: async (record) => {
      setActiveSavedStrategyId(record.strategy_id);
      await queryClient.invalidateQueries({ queryKey: ["saved-strategies"] });
    },
  });

  const deleteStrategyMutation = useMutation({
    mutationFn: (strategyId: string) => api.deleteSavedStrategy(strategyId),
    onSuccess: async (_result, strategyId) => {
      if (strategyId === activeSavedStrategyId) {
        setActiveSavedStrategyId(undefined);
      }
      await queryClient.invalidateQueries({ queryKey: ["saved-strategies"] });
    },
  });

  const { quoteStatus, chainStatus } = useMarketStreams(symbol, activeSelectedExpiration, {
    enableQuotes: summaryQuery.isSuccess,
    enableChain: activeView === "chain" && Boolean(activeChain),
  });
  const summaryErrorMessage = summaryQuery.error
    ? `${apiErrorLabel(summaryQuery.error)}: ${apiErrorMessage(summaryQuery.error, "Underlying summary unavailable.")}`
    : undefined;
  const chainErrorMessage = chainQuery.error
    ? `${apiErrorLabel(chainQuery.error)}: ${apiErrorMessage(chainQuery.error, "Option chain unavailable.")}`
    : undefined;
  const valuationErrorMessage = strategyValuationQuery.error
    ? `${apiErrorLabel(strategyValuationQuery.error)}: ${apiErrorMessage(strategyValuationQuery.error, "Strategy pricing unavailable.")}`
    : undefined;
  const scenarioErrorMessage = scenarioGridQuery.error
    ? `${apiErrorLabel(scenarioGridQuery.error)}: ${apiErrorMessage(scenarioGridQuery.error, "Scenario analysis unavailable.")}`
    : undefined;
  const savedStrategiesErrorMessage = savedStrategiesQuery.error
    ? `${apiErrorLabel(savedStrategiesQuery.error)}: ${apiErrorMessage(savedStrategiesQuery.error, "Saved strategies unavailable.")}`
    : undefined;
  const savedStrategyOperationError = saveStrategyMutation.error ?? deleteStrategyMutation.error;
  const savedStrategyOperationErrorMessage = savedStrategyOperationError
    ? `${apiErrorLabel(savedStrategyOperationError)}: ${apiErrorMessage(savedStrategyOperationError, "Local persistence operation failed.")}`
    : undefined;
  const streamMessage =
    chainStatus.message ??
    quoteStatus.message ??
    summaryErrorMessage ??
    chainErrorMessage ??
    (summaryQuery.isFetching || chainQuery.isFetching ? "Refreshing market data..." : undefined);

  useEffect(() => {
    if (activeSummary && isFiniteNumber(activeSummary.spot) && activeSummary.spot > 0) {
      syncUnderlying(activeSummary.symbol, activeSummary.spot);
    }
  }, [activeSummary, syncUnderlying]);

  useEffect(() => {
    if (!activeChain) {
      return;
    }

    queryClient.setQueryData(["chain", symbol, activeChain.selected_expiration], activeChain);
    reconcileChainSelection(activeChain);
  }, [activeChain, queryClient, reconcileChainSelection, symbol]);

  useEffect(() => {
    if (watchlistQuery.data?.length) {
      setWatchlistSymbols(watchlistQuery.data.map((item) => item.symbol));
    }
  }, [setWatchlistSymbols, watchlistQuery.data]);

  return (
    <div className="h-screen p-2">
      <PanelGroup orientation="horizontal" className="h-full gap-2">
        <Panel defaultSize={18} minSize={14}>
          <Sidebar
            currentSymbol={symbol}
            watchlistSymbols={watchlistSymbols}
            onSelectSymbol={setSymbol}
            onAddWatchlist={(watchSymbol) => addWatchlistMutation.mutate(watchSymbol)}
          />
        </Panel>

        <PanelResizeHandle className="w-2 rounded-full bg-[var(--panel-border)]/40 transition-colors hover:bg-[var(--accent)]/30" />

        <Panel defaultSize={58} minSize={42}>
          <div className="panel-surface flex h-full flex-col rounded-2xl p-3">
            <div className="mb-3 flex items-start justify-between gap-4 rounded-2xl border border-[var(--panel-border)] bg-[var(--panel-strong)] p-4">
              <div>
                <div className="metric-label mb-1">Options Analytics Workstation · v0.1 research beta</div>
                <div className="flex items-center gap-2">
                  <h1 className="text-2xl font-semibold tracking-tight">{symbol}</h1>
                  <Badge>{formatMarketDataMode(activeSummary?.market_data_mode)}</Badge>
                  {activeSummary?.is_delayed ? <Badge>Delayed</Badge> : null}
                </div>
                <div className="mt-1 text-sm text-[var(--muted-foreground)]">
                  {activeSummary?.description ?? (summaryErrorMessage ? "Underlying summary unavailable" : "Loading underlying summary")} |{" "}
                  {activeSummary?.exchange ?? "--"} | {activeSummary?.currency ?? "--"}
                </div>
                {streamMessage ? (
                  <div className="mt-2 text-xs text-[var(--warning)]">{streamMessage}</div>
                ) : null}
              </div>
              <div className="grid grid-cols-3 gap-6">
                <div>
                  <div className="metric-label">Spot</div>
                   <div className="metric-value">{formatPrice(activeSummary?.spot)}</div>
                </div>
                <div>
                  <div className="metric-label">Prev Close</div>
                   <div className="metric-value">{formatPrice(activeSummary?.previous_close)}</div>
                </div>
                <div>
                  <div className="metric-label">Daily Move</div>
                  <div className={`metric-value ${(activeSummary?.change ?? 0) >= 0 ? "number-positive" : "number-negative"}`}>
                     {activeSummary ? formatSignedPercent(activeSummary.change_percent) : "--"}
                  </div>
                </div>
              </div>
            </div>

            <Tabs value={activeView} onValueChange={(value) => setActiveView(value as typeof activeView)} className="flex min-h-0 flex-1 flex-col">
              <div className="mb-3 flex items-center justify-between">
                <TabsList>
                  <TabsTrigger value="chain">
                    <Clock3 className="size-4" />
                    Chain
                  </TabsTrigger>
                  <TabsTrigger value="strategy">
                    <BriefcaseBusiness className="size-4" />
                    Strategy
                  </TabsTrigger>
                  <TabsTrigger value="analytics">
                    <BarChart3 className="size-4" />
                    Analytics
                  </TabsTrigger>
                </TabsList>
                <div className="flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
                  <Waves className="size-4 text-[var(--accent)]" />
                  {strategy.legs.length} {strategy.legs.length === 1 ? "leg" : "legs"} staged
                </div>
              </div>

              <TabsContent value="chain" className="min-h-0 flex-1">
                <ChainExplorer
                  chain={activeChain}
                  selectedContract={activeSelectedContract}
                  selectedExpiration={activeSelectedExpiration}
                  filters={filters}
                  pinnedContracts={pinnedContracts}
                  loading={!activeChain && (summaryQuery.isLoading || chainQuery.isLoading)}
                  refreshing={chainQuery.isFetching && Boolean(activeChain)}
                  onSelectExpiration={setSelectedExpiration}
                  onSelectContract={setSelectedContract}
                  onAddLong={(quote) =>
                    addStrategyLeg({
                      leg_id: crypto.randomUUID(),
                      instrument_type: "option",
                      side: "long",
                      quantity: 1,
                      contract: quote.contract,
                      quote,
                      entry_price: getStagedOptionEntryPrice(quote),
                    })
                  }
                  onAddShort={(quote) =>
                    addStrategyLeg({
                      leg_id: crypto.randomUUID(),
                      instrument_type: "option",
                      side: "short",
                      quantity: 1,
                      contract: quote.contract,
                      quote,
                      entry_price: getStagedOptionEntryPrice(quote),
                    })
                  }
                  onTogglePinned={togglePinnedContract}
                   onUpdateFilters={updateFilters}
                   errorMessage={chainErrorMessage}
                   retryable={isRetryableApiError(chainQuery.error)}
                   onRetry={() => void chainQuery.refetch()}
                />
              </TabsContent>

              <TabsContent value="strategy" className="min-h-0 flex-1">
                <StrategyBuilder
                  chain={activeChain}
                  selectedContract={activeSelectedContract}
                  strategy={pricedStrategy}
                  valuation={strategyValuationQuery.data}
                   valuationLoading={pricingLoading}
                   valuationError={valuationErrorMessage}
                   valuationRetryable={isRetryableApiError(strategyValuationQuery.error)}
                   onRetryValuation={() => void strategyValuationQuery.refetch()}
                  onTemplateSelect={(template) => {
                    if (!activeChain) return;
                    const legs = buildTemplate(activeChain, template, activeSelectedContract);
                    replaceStrategy(template.replaceAll("_", " "), legs);
                  }}
                  onRemoveLeg={removeStrategyLeg}
                  onClearStrategy={clearStrategy}
                  savedStrategies={savedStrategiesQuery.data ?? []}
                  activeSavedStrategyId={activeSavedStrategyId}
                  savedStrategiesLoading={savedStrategiesQuery.isLoading}
                  savedStrategiesError={savedStrategiesErrorMessage}
                  savedStrategyOperationError={savedStrategyOperationErrorMessage}
                  canSaveStrategy={pricingReady}
                  strategySaving={saveStrategyMutation.isPending}
                  deletingStrategyId={deleteStrategyMutation.isPending ? deleteStrategyMutation.variables : undefined}
                  onSaveStrategy={() => saveStrategyMutation.mutate()}
                  onLoadStrategy={(record) => {
                    if (record.strategy.underlying_symbol !== symbol) {
                      setSymbol(record.strategy.underlying_symbol);
                    }
                    replaceStrategy(record.name, record.strategy.legs);
                    setActiveSavedStrategyId(record.strategy_id);
                    setActiveView("strategy");
                  }}
                  onDeleteStrategy={(strategyId) => deleteStrategyMutation.mutate(strategyId)}
                  onRetrySavedStrategies={() => void savedStrategiesQuery.refetch()}
                />
              </TabsContent>

              <TabsContent value="analytics" className="min-h-0 flex-1 overflow-x-hidden overflow-y-auto pr-1">
                <VolatilityPanel
                  skew={skewQuery.data ?? []}
                  termStructure={termStructureQuery.data ?? []}
                  scenario={scenarioGridQuery.data}
                  skewLoading={skewQuery.isLoading || skewQuery.isFetching}
                  termStructureLoading={termStructureQuery.isLoading || termStructureQuery.isFetching}
                  scenarioLoading={
                    (hasStagedStrategy && !debouncedPricingReady) || scenarioGridQuery.isLoading || scenarioGridQuery.isFetching
                  }
                   hasStrategy={hasStagedStrategy}
                   scenarioError={scenarioErrorMessage}
                   scenarioRetryable={isRetryableApiError(scenarioGridQuery.error)}
                   onRetryScenario={() => void scenarioGridQuery.refetch()}
                />
              </TabsContent>
            </Tabs>
          </div>
        </Panel>

        <PanelResizeHandle className="w-2 rounded-full bg-[var(--panel-border)]/40 transition-colors hover:bg-[var(--accent)]/30" />

        <Panel defaultSize={24} minSize={18}>
          <RightPanel
            summary={activeSummary}
            selectedContract={activeSelectedContract}
            assumptions={assumptions}
            valuation={strategyValuationQuery.data}
            valuationLoading={pricingLoading}
            hasStrategy={hasStagedStrategy}
            stagedLegCount={strategy.legs.length}
            onUpdateAssumptions={updateAssumptions}
            onAddSelectedLong={() => {
              if (!activeSelectedContract) return;
              addStrategyLeg({
                leg_id: crypto.randomUUID(),
                instrument_type: "option",
                side: "long",
                quantity: 1,
                contract: activeSelectedContract.contract,
                quote: activeSelectedContract,
                entry_price: getStagedOptionEntryPrice(activeSelectedContract),
              });
            }}
            onAddSelectedShort={() => {
              if (!activeSelectedContract) return;
              addStrategyLeg({
                leg_id: crypto.randomUUID(),
                instrument_type: "option",
                side: "short",
                quantity: 1,
                contract: activeSelectedContract.contract,
                quote: activeSelectedContract,
                entry_price: getStagedOptionEntryPrice(activeSelectedContract),
              });
            }}
          />
        </Panel>
      </PanelGroup>
    </div>
  );
}
