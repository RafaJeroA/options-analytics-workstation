"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

import { DataState } from "@/components/ui/data-state";
import { isFiniteNumber } from "@/lib/format";
import type { PayoffPoint } from "@/lib/types";

interface StrategyPayoffChartProps {
  payoff: PayoffPoint[];
  loading?: boolean;
  emptyMessage?: string;
}

function formatCompactCurrency(value: number): string {
  const roundedThousands = Math.round(Math.abs(value) / 1000);
  return `${value < 0 ? "-" : ""}$${roundedThousands}k`;
}

export function StrategyPayoffChart({ payoff, loading = false, emptyMessage }: StrategyPayoffChartProps) {
  const safePayoff = payoff.filter((point) => isFiniteNumber(point.spot) && isFiniteNumber(point.value));
  return (
    <div className="flex h-72 min-w-0 flex-col rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)] p-3">
      <div className="mb-2">
        <div className="metric-label">Expiry Payoff</div>
      </div>
      {loading && !safePayoff.length ? (
        <DataState message="Loading analytics..." tone="loading" />
      ) : safePayoff.length ? (
        <div className="min-h-0 min-w-0 flex-1">
          <ResponsiveContainer width="100%" height="100%" minWidth={0} initialDimension={{ width: 640, height: 240 }}>
            <AreaChart data={safePayoff} margin={{ top: 8, right: 16, bottom: 24, left: 8 }}>
              <defs>
                <linearGradient id="payoff-gradient" x1="0" x2="0" y1="0" y2="1">
                  <stop offset="0%" stopColor="#6ee7b7" stopOpacity={0.35} />
                  <stop offset="100%" stopColor="#6ee7b7" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <CartesianGrid stroke="rgba(109,129,154,0.16)" vertical={false} />
              <XAxis
                dataKey="spot"
                type="number"
                domain={["dataMin", "dataMax"]}
                allowDecimals={false}
                stroke="#8ea0b8"
                tick={{ fill: "#8ea0b8", fontSize: 11 }}
                tickFormatter={(value: number) => value.toFixed(0)}
                label={{
                  value: "Underlying at expiry",
                  position: "insideBottom",
                  offset: -16,
                  fill: "#8ea0b8",
                  fontSize: 11,
                }}
              />
              <YAxis
                stroke="#8ea0b8"
                tick={{ fill: "#8ea0b8", fontSize: 11 }}
                tickFormatter={formatCompactCurrency}
                width={48}
              />
              <Tooltip
                contentStyle={{
                  background: "rgba(10,16,25,0.96)",
                  border: "1px solid rgba(109,129,154,0.24)",
                  color: "#edf2f7",
                }}
              />
              <Area
                type="linear"
                dataKey="value"
                stroke="#6ee7b7"
                fill="url(#payoff-gradient)"
                strokeWidth={2}
                isAnimationActive={false}
              />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      ) : (
        <DataState message={emptyMessage ?? "Payoff is unavailable for the current strategy."} tone="warning" />
      )}
    </div>
  );
}
