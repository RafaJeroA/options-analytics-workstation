"use client";

import { Activity, ArrowDownToLine, ArrowUpToLine } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataState } from "@/components/ui/data-state";
import { Input } from "@/components/ui/input";
import { Separator } from "@/components/ui/separator";
import {
  formatMarketDataMode,
  formatPayoffMetric,
  formatPercent,
  formatPrice,
  formatQuoteSource,
  formatSignedNumber,
} from "@/lib/format";
import { getStagedOptionEntryPrice } from "@/lib/strategy-pricing";
import type { OptionQuote, PricingAssumptions, StrategyValuation, UnderlyingQuote } from "@/lib/types";

interface RightPanelProps {
  summary?: UnderlyingQuote;
  selectedContract?: OptionQuote;
  assumptions: PricingAssumptions;
  valuation?: StrategyValuation;
  valuationLoading?: boolean;
  hasStrategy?: boolean;
  stagedLegCount?: number;
  onUpdateAssumptions: (partial: Partial<PricingAssumptions>) => void;
  onAddSelectedLong: () => void;
  onAddSelectedShort: () => void;
}

export function RightPanel({
  summary,
  selectedContract,
  assumptions,
  valuation,
  valuationLoading = false,
  hasStrategy = false,
  stagedLegCount = 0,
  onUpdateAssumptions,
  onAddSelectedLong,
  onAddSelectedShort,
}: RightPanelProps) {
  const maxProfitLabel = valuation
    ? formatPayoffMetric(valuation.max_profit, valuation.max_profit_state)
    : "--";
  const maxLossLabel = valuation ? formatPayoffMetric(valuation.max_loss, valuation.max_loss_state) : "--";
  const canStageSelected = getStagedOptionEntryPrice(selectedContract) !== undefined;

  function updateFiniteAssumption(field: keyof PricingAssumptions, value: number, minimum?: number) {
    if (Number.isFinite(value) && (minimum === undefined || value >= minimum)) {
      onUpdateAssumptions({ [field]: value });
    }
  }

  return (
    <div className="panel-surface flex h-full flex-col gap-3 overflow-y-auto rounded-2xl p-3">
      <Card className="border-none bg-transparent shadow-none">
        <CardHeader className="px-0 pb-2 pt-0">
          <CardTitle>Inspector</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 px-0 pb-0">
          <div className="rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)] p-3">
            <div className="metric-label">Underlying</div>
            <div className="mt-1 text-lg font-semibold">{summary?.symbol ?? "--"}</div>
            <div className="text-xs text-[var(--muted-foreground)]">{summary?.description ?? "Select a symbol"}</div>
            {summary ? <Badge className="mt-2">{formatMarketDataMode(summary.market_data_mode)}</Badge> : null}
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <div className="metric-label">Spot</div>
                <div className="metric-value">{formatPrice(summary?.spot)}</div>
              </div>
              <div>
                <div className="metric-label">Move</div>
                <div className={`metric-value ${(summary?.change ?? 0) >= 0 ? "number-positive" : "number-negative"}`}>
                  {summary ? formatSignedNumber(summary.change) : "--"}
                </div>
              </div>
            </div>
          </div>

          <div className="rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)] p-3">
            <div className="flex items-center justify-between">
              <div className="metric-label">Selected Contract</div>
              {selectedContract ? <Badge>{selectedContract.contract.right}</Badge> : null}
            </div>
            {selectedContract ? (
              <div className="mt-2 grid gap-2">
                <div className="text-sm font-semibold">
                  {selectedContract.contract.symbol} {selectedContract.contract.expiration} {selectedContract.contract.strike}
                </div>
                <div className="grid grid-cols-2 gap-2 text-xs text-[var(--muted-foreground)]">
                  <div>Mark: {formatPrice(selectedContract.mark)}</div>
                  <div>IV: {formatPercent(selectedContract.implied_vol, 1)}</div>
                  <div>Delta: {formatSignedNumber(selectedContract.greeks?.delta, 3)}</div>
                  <div>Theta: {formatSignedNumber(selectedContract.greeks?.theta, 3)}</div>
                </div>
                <div className="flex flex-wrap gap-2">
                  <Badge>{formatMarketDataMode(selectedContract.market_data_mode)}</Badge>
                  <Badge>{formatQuoteSource(selectedContract.quote_source)}</Badge>
                  <Badge>{formatQuoteSource(selectedContract.model_source)}</Badge>
                  {selectedContract.data_flags.map((flag) => (
                    <Badge key={flag}>{flag.replaceAll("_", " ")}</Badge>
                  ))}
                </div>
                {selectedContract.market_data_unavailable || selectedContract.subscription_missing ? (
                  <div className="rounded-xl border border-[var(--panel-border)] bg-[var(--panel)] p-3 text-xs text-[var(--muted-foreground)]">
                    Quote data is limited for this contract. Staged pricing may remain partial until a usable premium arrives.
                  </div>
                ) : null}
                <div className="flex gap-2">
                  <Button size="sm" onClick={onAddSelectedLong} disabled={!canStageSelected}>
                    <ArrowDownToLine className="size-4" />
                    Add Long
                  </Button>
                  <Button size="sm" variant="secondary" onClick={onAddSelectedShort} disabled={!canStageSelected}>
                    <ArrowUpToLine className="size-4" />
                    Add Short
                  </Button>
                </div>
              </div>
            ) : (
              <div className="mt-2 text-xs text-[var(--muted-foreground)]">
                {stagedLegCount > 0
                  ? `No contract selected. ${stagedLegCount} staged ${stagedLegCount === 1 ? "leg remains" : "legs remain"} active in Strategy. Select a chain row to inspect another contract.`
                  : "No contract selected. Select a chain row to inspect and stage it."}
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      <Separator />

      <Card className="border-none bg-transparent shadow-none">
        <CardHeader className="px-0 pb-2 pt-0">
          <CardTitle>Assumptions</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-3 px-0 pb-0">
          <label className="grid gap-1">
            <span className="metric-label">Risk-Free Rate</span>
            <Input
              type="number"
              step="0.001"
              value={assumptions.risk_free_rate}
              onChange={(event) => updateFiniteAssumption("risk_free_rate", event.currentTarget.valueAsNumber)}
            />
          </label>
          <label className="grid gap-1">
            <span className="metric-label">Dividend Yield</span>
            <Input
              type="number"
              step="0.001"
              value={assumptions.dividend_yield}
              onChange={(event) => updateFiniteAssumption("dividend_yield", event.currentTarget.valueAsNumber)}
            />
          </label>
          <label className="grid gap-1">
            <span className="metric-label">Volatility Shift</span>
            <Input
              type="number"
              step="0.01"
              value={assumptions.volatility_shift}
              onChange={(event) => updateFiniteAssumption("volatility_shift", event.currentTarget.valueAsNumber)}
            />
          </label>
          <label className="grid gap-1">
            <span className="metric-label">Days Forward</span>
            <Input
              type="number"
              step="1"
              min="0"
              value={assumptions.days_forward}
              onChange={(event) =>
                updateFiniteAssumption("days_forward", Math.trunc(event.currentTarget.valueAsNumber), 0)
              }
            />
          </label>
        </CardContent>
      </Card>

      <Separator />

      <Card className="border-none bg-transparent shadow-none">
        <CardHeader className="px-0 pb-2 pt-0">
          <CardTitle>Strategy Snapshot</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-2 px-0 pb-0 text-sm">
          {valuationLoading && !valuation ? (
            <DataState message="Loading analytics..." tone="loading" />
          ) : !hasStrategy ? (
            <DataState message="Stage a strategy to populate the snapshot." />
          ) : valuation ? (
            <>
              <div className="flex items-center justify-between">
                <span className="metric-label">Net Debit/Credit</span>
                <span>{formatPrice(valuation.net_debit_credit)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="metric-label">Theoretical</span>
                <span>{formatPrice(valuation.theoretical_value)}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="metric-label">Open PnL</span>
                <span
                  className={
                    valuation.pnl_open === null || valuation.pnl_open === undefined
                      ? ""
                      : valuation.pnl_open >= 0
                        ? "number-positive"
                        : "number-negative"
                  }
                >
                  {formatPrice(valuation.pnl_open)}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="metric-label">Max Profit</span>
                <span>{maxProfitLabel}</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="metric-label">Max Loss</span>
                <span>{maxLossLabel}</span>
              </div>
              {valuation.status_message ? (
                <div className="mt-2 rounded-xl border border-[var(--panel-border)] bg-[var(--panel)] p-3 text-xs text-[var(--muted-foreground)]">
                  {valuation.status_message}
                </div>
              ) : null}
            </>
          ) : (
            <DataState message="Strategy snapshot is unavailable." tone="warning" />
          )}
          <div className="mt-2 rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)] p-3 text-xs text-[var(--muted-foreground)]">
            <Activity className="mb-2 size-4 text-[var(--accent)]" />
            Broker model values and locally estimated Greeks remain separate throughout the UI. Wide, stale, crossed, and IV-invalid quotes are flagged in the chain before they influence analytics.
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
