"use client";

import { Trash2 } from "lucide-react";

import { StrategyPayoffChart } from "@/components/strategy/strategy-payoff-chart";
import { SavedStrategyPanel } from "@/components/strategy/saved-strategy-panel";
import { StrategySummary } from "@/components/strategy/strategy-summary";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatPrice, formatQuoteSource } from "@/lib/format";
import { payoffMetricsAvailable } from "@/lib/strategy-pricing";
import { buildTemplate } from "@/lib/strategy-templates";
import type {
  ChainSnapshot,
  OptionQuote,
  SavedStrategyRecord,
  StrategyDefinition,
  StrategyValuation,
} from "@/lib/types";

const templates = [
  ["long_call", "Long Call"],
  ["short_call", "Short Call"],
  ["long_put", "Long Put"],
  ["short_put", "Short Put"],
  ["covered_call", "Covered Call"],
  ["cash_secured_put", "Cash-Secured Put"],
  ["vertical_spread", "Vertical Spread"],
  ["straddle", "Straddle"],
  ["strangle", "Strangle"],
  ["iron_condor", "Iron Condor"],
  ["butterfly", "Butterfly"],
] as const;

interface StrategyBuilderProps {
  chain?: ChainSnapshot;
  selectedContract?: OptionQuote;
  strategy: StrategyDefinition;
  valuation?: StrategyValuation;
  valuationLoading?: boolean;
  valuationError?: string;
  valuationRetryable?: boolean;
  onRetryValuation?: () => void;
  onTemplateSelect: (template: string) => void;
  onRemoveLeg: (legId: string) => void;
  onClearStrategy: () => void;
  savedStrategies: SavedStrategyRecord[];
  activeSavedStrategyId?: string;
  savedStrategiesLoading?: boolean;
  savedStrategiesError?: string;
  savedStrategyOperationError?: string;
  canSaveStrategy?: boolean;
  strategySaving?: boolean;
  deletingStrategyId?: string;
  onSaveStrategy: () => void;
  onLoadStrategy: (record: SavedStrategyRecord) => void;
  onDeleteStrategy: (strategyId: string) => void;
  onRetrySavedStrategies: () => void;
}

export function StrategyBuilder({
  chain,
  selectedContract,
  strategy,
  valuation,
  valuationLoading = false,
  valuationError,
  valuationRetryable = false,
  onRetryValuation,
  onTemplateSelect,
  onRemoveLeg,
  onClearStrategy,
  savedStrategies,
  activeSavedStrategyId,
  savedStrategiesLoading = false,
  savedStrategiesError,
  savedStrategyOperationError,
  canSaveStrategy = false,
  strategySaving = false,
  deletingStrategyId,
  onSaveStrategy,
  onLoadStrategy,
  onDeleteStrategy,
  onRetrySavedStrategies,
}: StrategyBuilderProps) {
  const activeValuation = strategy.legs.length ? valuation : undefined;
  const payoffEmptyMessage = !strategy.legs.length
    ? "Stage a strategy to view payoff."
    : activeValuation?.status_message ??
      (payoffMetricsAvailable(activeValuation)
        ? "Payoff is unavailable for the current strategy."
        : "Payoff unavailable: one or more legs have no usable entry premium.");

  return (
    <div className="grid h-full min-h-0 gap-3 xl:grid-cols-[1.1fr_0.9fr]">
      <div className="flex min-h-0 flex-col gap-3">
        <SavedStrategyPanel
          records={savedStrategies}
          activeStrategyId={activeSavedStrategyId}
          loading={savedStrategiesLoading}
          saving={strategySaving}
          deletingStrategyId={deletingStrategyId}
          errorMessage={savedStrategiesError}
          operationError={savedStrategyOperationError}
          canSave={canSaveStrategy}
          onSave={onSaveStrategy}
          onLoad={onLoadStrategy}
          onDelete={onDeleteStrategy}
          onRetry={onRetrySavedStrategies}
        />
        <Card>
          <CardHeader>
            <CardTitle>Templates</CardTitle>
          </CardHeader>
          <CardContent className="grid grid-cols-2 gap-2 xl:grid-cols-3">
            {templates.map(([value, label]) => (
              <Button
                key={value}
                size="sm"
                variant="secondary"
                disabled={!chain || buildTemplate(chain, value, selectedContract).length === 0}
                onClick={() => onTemplateSelect(value)}
              >
                {label}
              </Button>
            ))}
          </CardContent>
        </Card>

        <Card className="min-h-0 flex-1">
          <CardHeader>
            <CardTitle>
              {strategy.name} {selectedContract ? `| staged from ${selectedContract.contract.symbol}` : ""}
            </CardTitle>
          </CardHeader>
          <CardContent className="min-h-0">
            <div className="mb-3 flex items-center justify-between">
              <div className="text-xs text-[var(--muted-foreground)]">
                {strategy.legs.length} {strategy.legs.length === 1 ? "leg" : "legs"} |{" "}
                {chain?.selected_expiration ?? "--"} expiry context
              </div>
              <Button size="sm" variant="ghost" onClick={onClearStrategy}>
                Clear
              </Button>
            </div>
            <div className="rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)]">
              <table className="min-w-full text-sm">
                <thead className="text-[11px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
                  <tr className="[&>th]:border-b [&>th]:border-[var(--panel-border)] [&>th]:px-3 [&>th]:py-2 [&>th]:text-left">
                    <th>Side</th>
                    <th>Type</th>
                    <th>Contract</th>
                    <th>Qty</th>
                    <th>Entry</th>
                    <th>Source</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {strategy.legs.map((leg) => (
                    <tr className="border-b border-[var(--panel-border)] last:border-b-0" key={leg.leg_id}>
                      <td className="px-3 py-2 capitalize">{leg.side}</td>
                      <td className="px-3 py-2 capitalize">{leg.instrument_type}</td>
                      <td className="px-3 py-2">
                        {leg.instrument_type === "stock"
                          ? `${leg.underlying_symbol} shares`
                          : `${leg.contract?.symbol} ${leg.contract?.expiration} ${leg.contract?.strike} ${leg.contract?.right}`}
                      </td>
                      <td className="px-3 py-2">{leg.quantity}</td>
                      <td className="px-3 py-2">{formatPrice(leg.entry_price ?? leg.stock_price)}</td>
                      <td className="px-3 py-2 text-xs text-[var(--muted-foreground)]">
                        {leg.instrument_type === "stock" ? "User input" : formatQuoteSource(leg.quote?.quote_source)}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <Button size="icon" variant="ghost" onClick={() => onRemoveLeg(leg.leg_id)}>
                          <Trash2 className="size-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                  {!strategy.legs.length ? (
                    <tr>
                      <td className="px-3 py-8 text-center text-sm text-[var(--muted-foreground)]" colSpan={7}>
                        Add individual contracts from the chain or seed a template here.
                      </td>
                    </tr>
                  ) : null}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      </div>

      <div className="flex min-h-0 flex-col gap-3">
        <StrategySummary
          valuation={activeValuation}
          loading={valuationLoading}
          hasStrategy={strategy.legs.length > 0}
          errorMessage={valuationError}
          retryable={valuationRetryable}
          onRetry={onRetryValuation}
        />
        <StrategyPayoffChart
          payoff={activeValuation?.payoff ?? []}
          loading={valuationLoading}
          emptyMessage={payoffEmptyMessage}
        />
      </div>
    </div>
  );
}
