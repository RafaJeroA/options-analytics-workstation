"use client";

import { useMemo } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type TooltipContentProps,
  type TooltipValueType,
} from "recharts";

import { ScenarioGrid } from "@/components/analytics/scenario-grid";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataState } from "@/components/ui/data-state";
import {
  paddedNumericDomain,
  prepareSmileChartData,
  prepareTermChartData,
  type SmileChartPoint,
  type TermChartPoint,
} from "@/lib/analytics-chart-data";
import type { ScenarioGridResult, TermStructurePoint, VolSurfacePoint } from "@/lib/types";

interface VolatilityPanelProps {
  skew: VolSurfacePoint[];
  termStructure: TermStructurePoint[];
  scenario?: ScenarioGridResult;
  skewLoading?: boolean;
  termStructureLoading?: boolean;
  scenarioLoading?: boolean;
  hasStrategy?: boolean;
  scenarioError?: string;
  scenarioRetryable?: boolean;
  onRetryScenario?: () => void;
}

const tooltipStyle = {
  background: "rgba(10,16,25,0.98)",
  border: "1px solid rgba(109,129,154,0.35)",
  borderRadius: 10,
  boxShadow: "0 12px 30px rgba(0,0,0,0.35)",
};

function SmileTooltip({ active, payload }: TooltipContentProps<TooltipValueType, number | string>) {
  const point = payload?.[0]?.payload as SmileChartPoint | undefined;
  if (!active || !point) return null;
  return (
    <div style={tooltipStyle} className="grid gap-1 p-3 text-xs">
      <div className="font-semibold">Strike {point.strike.toFixed(2)}</div>
      <div>IV: {point.iv.toFixed(1)}%</div>
      <div>Moneyness: {(point.moneyness * 100).toFixed(1)}%</div>
      <div>Expiration: {point.expiration}</div>
      <div>Source: {point.method}</div>
    </div>
  );
}

function TermTooltip({ active, payload }: TooltipContentProps<TooltipValueType, number | string>) {
  const point = payload?.[0]?.payload as TermChartPoint | undefined;
  if (!active || !point) return null;
  return (
    <div style={tooltipStyle} className="grid gap-1 p-3 text-xs">
      <div className="font-semibold">{point.expiration}</div>
      <div>DTE: {point.days} days</div>
      <div>ATM IV: {point.iv.toFixed(1)}%</div>
      <div>ATM strike: {point.atmStrike.toFixed(2)}</div>
      <div>
        {point.method} (n={point.sampleSize})
      </div>
    </div>
  );
}

export function VolatilityPanel({
  skew,
  termStructure,
  scenario,
  skewLoading = false,
  termStructureLoading = false,
  scenarioLoading = false,
  hasStrategy = false,
  scenarioError,
  scenarioRetryable = false,
  onRetryScenario,
}: VolatilityPanelProps) {
  const skewData = useMemo(() => prepareSmileChartData(skew), [skew]);
  const termData = useMemo(() => prepareTermChartData(termStructure), [termStructure]);
  const skewStrikeDomain = useMemo(
    () => paddedNumericDomain(skewData.map((point) => point.strike), { minimumSpan: 10 }),
    [skewData]
  );
  const skewIvDomain = useMemo(
    () => paddedNumericDomain(skewData.map((point) => point.iv), { minimumSpan: 8 }),
    [skewData]
  );
  const termDaysDomain = useMemo(
    () => paddedNumericDomain(termData.map((point) => point.days), { minimumSpan: 14 }),
    [termData]
  );
  const termIvDomain = useMemo(
    () => paddedNumericDomain(termData.map((point) => point.iv), { minimumSpan: 4 }),
    [termData]
  );
  const unavailableExpirations = termStructure.filter((point) => point.status !== "available").length;

  return (
    <div className="grid content-start gap-4 xl:grid-cols-2">
      <Card data-testid="smile-skew-card" className="min-h-[410px] overflow-visible">
        <CardHeader className="items-start gap-3">
          <div>
            <CardTitle>Volatility Smile / Skew</CardTitle>
            <div className="mt-1 text-xs text-[var(--muted-foreground)]">
              OTM composite: puts below spot, calls above spot, call/put mean at ATM
            </div>
          </div>
        </CardHeader>
        <CardContent className="h-[340px] overflow-visible">
          {skewLoading && skewData.length < 3 ? (
            <DataState message="Loading analytics..." tone="loading" />
          ) : skewData.length < 3 ? (
            <DataState
              message={`Insufficient smile data: ${skewData.length} valid strike${skewData.length === 1 ? "" : "s"}; at least 3 are required.`}
              tone="warning"
            />
          ) : (
            <div
              className="h-full"
              role="img"
              aria-label="Volatility smile chart. X-axis: Strike. Y-axis: Implied volatility percent."
            >
              <ResponsiveContainer
                width="100%"
                height="100%"
                minWidth={0}
                initialDimension={{ width: 640, height: 340 }}
              >
                <LineChart data={skewData} margin={{ top: 12, right: 24, bottom: 38, left: 18 }}>
                <CartesianGrid stroke="rgba(109,129,154,0.16)" />
                <XAxis
                  dataKey="strike"
                  type="number"
                  domain={skewStrikeDomain}
                  tick={{ fill: "#8ea0b8", fontSize: 11 }}
                  tickFormatter={(value: number) => value.toFixed(0)}
                  stroke="#8ea0b8"
                  label={{ value: "Strike", position: "insideBottom", offset: -24, fill: "#8ea0b8", fontSize: 11 }}
                />
                <YAxis
                  domain={skewIvDomain}
                  tick={{ fill: "#8ea0b8", fontSize: 11 }}
                  tickFormatter={(value: number) => `${value.toFixed(0)}%`}
                  stroke="#8ea0b8"
                  width={52}
                  label={{ value: "Implied volatility (%)", angle: -90, position: "insideLeft", offset: -5, fill: "#8ea0b8", fontSize: 11 }}
                />
                <Tooltip
                  content={SmileTooltip}
                  cursor={{ stroke: "rgba(110,231,183,0.35)" }}
                />
                <Legend verticalAlign="top" height={30} />
                <Line
                  dataKey="iv"
                  name="OTM composite IV"
                  stroke="#6ee7b7"
                  strokeWidth={2.5}
                  dot={{ r: 3, fill: "#6ee7b7", strokeWidth: 0 }}
                  activeDot={{ r: 5 }}
                  isAnimationActive={false}
                />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      <Card data-testid="term-structure-card" className="min-h-[410px] overflow-visible">
        <CardHeader className="items-start gap-3">
          <div>
            <CardTitle>ATM Volatility Term Structure</CardTitle>
            <div className="mt-1 text-xs text-[var(--muted-foreground)]">
              Nearest-strike call/put mean across chronological expirations
            </div>
          </div>
          <div className="text-right text-xs text-[var(--muted-foreground)]">
            {termData.length} usable
            {unavailableExpirations ? ` / ${unavailableExpirations} unavailable` : ""}
          </div>
        </CardHeader>
        <CardContent className="h-[340px] overflow-visible">
          {termStructureLoading && termData.length < 2 ? (
            <DataState message="Loading analytics..." tone="loading" />
          ) : termData.length < 2 ? (
            <DataState
              message={`Insufficient term data: ${termData.length} usable expiration${termData.length === 1 ? "" : "s"}; at least 2 are required.`}
              tone="warning"
            />
          ) : (
            <div
              className="h-full"
              role="img"
              aria-label="ATM volatility term chart. X-axis: Days to expiry. Y-axis: ATM implied volatility percent."
            >
              <ResponsiveContainer
                width="100%"
                height="100%"
                minWidth={0}
                initialDimension={{ width: 640, height: 340 }}
              >
                <LineChart data={termData} margin={{ top: 12, right: 24, bottom: 38, left: 18 }}>
                <CartesianGrid stroke="rgba(109,129,154,0.16)" />
                <XAxis
                  dataKey="days"
                  type="number"
                  domain={termDaysDomain}
                  ticks={termData.map((point) => point.days)}
                  allowDecimals={false}
                  tick={{ fill: "#8ea0b8", fontSize: 11 }}
                  tickFormatter={(value: number) => `${value}d`}
                  stroke="#8ea0b8"
                  label={{ value: "Days to expiry (DTE)", position: "insideBottom", offset: -24, fill: "#8ea0b8", fontSize: 11 }}
                />
                <YAxis
                  domain={termIvDomain}
                  tick={{ fill: "#8ea0b8", fontSize: 11 }}
                  tickFormatter={(value: number) => `${value.toFixed(0)}%`}
                  stroke="#8ea0b8"
                  width={52}
                  label={{ value: "ATM IV (%)", angle: -90, position: "insideLeft", offset: -5, fill: "#8ea0b8", fontSize: 11 }}
                />
                <Tooltip
                  content={TermTooltip}
                  cursor={{ stroke: "rgba(245,158,11,0.35)" }}
                />
                <Legend verticalAlign="top" height={30} />
                <Line
                  dataKey="iv"
                  name="ATM IV"
                  stroke="#f59e0b"
                  strokeWidth={2.5}
                  dot={{ r: 4, fill: "#f59e0b", strokeWidth: 0 }}
                  activeDot={{ r: 6 }}
                  isAnimationActive={false}
                />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </CardContent>
      </Card>

      <div className="relative z-10 xl:col-span-2">
        <ScenarioGrid
          scenario={scenario}
          loading={scenarioLoading}
          hasStrategy={hasStrategy}
          errorMessage={scenarioError}
          retryable={scenarioRetryable}
          onRetry={onRetryScenario}
        />
      </div>
    </div>
  );
}
