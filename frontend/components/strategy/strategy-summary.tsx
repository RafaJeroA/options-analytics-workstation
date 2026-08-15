import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataState } from "@/components/ui/data-state";
import { formatNumber, formatPayoffMetric, isFiniteNumber } from "@/lib/format";
import type { StrategyValuation } from "@/lib/types";

interface StrategySummaryProps {
  valuation?: StrategyValuation;
  loading?: boolean;
  hasStrategy?: boolean;
  errorMessage?: string;
  retryable?: boolean;
  onRetry?: () => void;
}

export function StrategySummary({
  valuation,
  loading = false,
  hasStrategy = false,
  errorMessage,
  retryable = false,
  onRetry,
}: StrategySummaryProps) {
  const maxProfitLabel = valuation
    ? formatPayoffMetric(valuation.max_profit, valuation.max_profit_state)
    : "--";
  const maxLossLabel = valuation ? formatPayoffMetric(valuation.max_loss, valuation.max_loss_state) : "--";
  const breakevenLabel = valuation
    ? valuation.breakeven_intervals.length
      ? valuation.breakeven_intervals
          .map((interval) =>
            interval.end === null
              ? `${formatNumber(interval.start)} to unlimited`
              : `${formatNumber(interval.start)} to ${formatNumber(interval.end)}`
          )
          .join(" / ")
      : valuation.breakevens.filter(isFiniteNumber).length
        ? valuation.breakevens.filter(isFiniteNumber).map((value) => formatNumber(value)).join(" / ")
        : valuation.max_profit_state === "unavailable" && valuation.max_loss_state === "unavailable"
          ? "Unavailable"
          : "None"
    : "--";

  return (
    <Card>
      <CardHeader>
        <CardTitle>Strategy Metrics</CardTitle>
      </CardHeader>
      <CardContent className="grid grid-cols-2 gap-3 text-sm">
        {loading && !valuation ? (
          <div className="col-span-2">
            <DataState message="Loading analytics..." tone="loading" />
          </div>
        ) : null}
        {!loading && !valuation && !hasStrategy ? (
          <div className="col-span-2">
            <DataState message="Stage a strategy to view snapshot metrics." />
          </div>
        ) : null}
        {!loading && !valuation && hasStrategy && errorMessage ? (
          <div className="col-span-2">
            <DataState
              message={errorMessage}
              tone="warning"
              actionLabel={retryable ? "Retry" : undefined}
              onAction={retryable ? onRetry : undefined}
            />
          </div>
        ) : null}
        {valuation ? (
          <>
            <div>
              <div className="metric-label">Entry Cost</div>
              <div className="metric-value">{formatPayoffMetric(valuation.entry_cost, "finite")}</div>
            </div>
            <div>
              <div className="metric-label">Current Value · quoted marks</div>
              <div className="metric-value">{formatPayoffMetric(valuation.current_value, "finite")}</div>
            </div>
            <div className="col-span-2">
              <div className="metric-label">Theoretical Value · local model</div>
              <div className="metric-value">{formatPayoffMetric(valuation.theoretical_value, "finite")}</div>
            </div>
            <div>
              <div className="metric-label">Max Profit</div>
              <div className="metric-value">{maxProfitLabel}</div>
            </div>
            <div>
              <div className="metric-label">Max Loss</div>
              <div className="metric-value">{maxLossLabel}</div>
            </div>
            <div className="col-span-2">
              <div className="metric-label">Breakevens</div>
              <div className="metric-value">{breakevenLabel}</div>
            </div>
            {valuation.status_message ? (
              <div className="col-span-2 rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)] p-3 text-xs text-[var(--muted-foreground)]">
                {valuation.status_message}
              </div>
            ) : null}
          </>
        ) : null}
      </CardContent>
    </Card>
  );
}
