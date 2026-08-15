"use client";

import { useEffect, useMemo, useState } from "react";

import { DataState } from "@/components/ui/data-state";
import { Button } from "@/components/ui/button";
import { formatPrice, formatSignedPercent, isFiniteNumber } from "@/lib/format";
import type { ScenarioGridResult } from "@/lib/types";

interface ScenarioGridProps {
  scenario?: ScenarioGridResult;
  loading?: boolean;
  hasStrategy?: boolean;
  errorMessage?: string;
  retryable?: boolean;
  onRetry?: () => void;
}

export function scenarioCellKey(days: number, move: number, shift: number) {
  return `${days}:${move}:${shift}`;
}

export function ScenarioGrid({
  scenario,
  loading = false,
  hasStrategy = false,
  errorMessage,
  retryable = false,
  onRetry,
}: ScenarioGridProps) {
  const points = useMemo(
    () =>
      (scenario?.points ?? []).filter(
        (point) =>
          isFiniteNumber(point.days_forward) &&
          isFiniteNumber(point.move_pct) &&
          isFiniteNumber(point.vol_shift) &&
          isFiniteNumber(point.underlying_price)
      ),
    [scenario?.points]
  );
  const days = useMemo(
    () => [...new Set(points.map((point) => point.days_forward))].sort((left, right) => left - right),
    [points]
  );
  const [selectedDay, setSelectedDay] = useState(0);

  useEffect(() => {
    if (days.length && !days.includes(selectedDay)) {
      setSelectedDay(days[0]);
    }
  }, [days, selectedDay]);

  const selectedPoints = useMemo(
    () => points.filter((point) => point.days_forward === selectedDay),
    [points, selectedDay]
  );
  const moves = useMemo(
    () => [...new Set(selectedPoints.map((point) => point.move_pct))].sort((left, right) => left - right),
    [selectedPoints]
  );
  const shifts = useMemo(
    () => [...new Set(selectedPoints.map((point) => point.vol_shift))].sort((left, right) => left - right),
    [selectedPoints]
  );
  const selectedDayState = scenario?.day_states.find((state) => state.days_forward === selectedDay);
  const volatilityDimensionMuted = selectedDayState?.volatility_shift_effective === false;
  const displayedShifts = useMemo(() => {
    if (!volatilityDimensionMuted || shifts.length <= 1) {
      return shifts;
    }
    return [shifts.reduce((closest, shift) => (Math.abs(shift) < Math.abs(closest) ? shift : closest))];
  }, [shifts, volatilityDimensionMuted]);
  const byCell = useMemo(
    () =>
      new Map(
        points.map((point) => [
          scenarioCellKey(point.days_forward, point.move_pct, point.vol_shift),
          point,
        ])
      ),
    [points]
  );

  return (
    <div
      className="rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)] p-3"
      data-testid="scenario-grid"
    >
      <div className="mb-2 flex flex-wrap items-start justify-between gap-2">
        <div>
          <div className="metric-label">Scenario Grid</div>
          <div className="text-xs text-[var(--muted-foreground)]">Theoretical PnL by spot, volatility, and forward day</div>
        </div>
        {days.length > 1 ? (
          <div aria-label="Forward day" className="flex flex-wrap gap-1">
            {days.map((day) => (
              <Button
                key={day}
                size="sm"
                variant={selectedDay === day ? "default" : "secondary"}
                onClick={() => setSelectedDay(day)}
              >
                {day === 0 ? "Today" : `+${day}d`}
              </Button>
            ))}
          </div>
        ) : null}
      </div>
      {scenario?.warnings.length ? (
        <div className="mb-3 rounded-xl border border-[var(--panel-border)] bg-[var(--panel)] p-3 text-xs text-[var(--muted-foreground)]">
          {scenario.warnings.join(" ")}
        </div>
      ) : null}
      {loading && !points.length ? (
        <DataState message="Loading analytics..." tone="loading" />
      ) : !hasStrategy ? (
        <DataState message="Stage a strategy to compute scenario grid." />
      ) : errorMessage && !points.length ? (
        <DataState
          message={errorMessage}
          tone="warning"
          actionLabel={retryable ? "Retry" : undefined}
          onAction={retryable ? onRetry : undefined}
        />
      ) : !points.length ? (
        <DataState message={scenario?.status_message ?? "Scenario grid is unavailable for the current strategy."} tone="warning" />
      ) : (
        <div className="overflow-auto">
          <div className="mb-2 text-xs text-[var(--muted-foreground)]">
            Forward date: {selectedDay === 0 ? "today" : `+${selectedDay} calendar days`}
          </div>
          {selectedDayState?.message ? (
            <div
              className="mb-3 rounded-lg border border-[var(--panel-border)] bg-[var(--panel)] px-3 py-2 text-xs text-[var(--muted-foreground)]"
              data-testid="scenario-day-state"
            >
              {selectedDayState.message}
            </div>
          ) : null}
          <table className="min-w-full text-[11px]">
            <thead>
              <tr className="[&>th]:px-2 [&>th]:py-2 [&>th]:text-[var(--muted-foreground)]">
                <th className="text-left">Spot \ Vol</th>
                {displayedShifts.map((shift) => (
                  <th key={shift}>
                    {volatilityDimensionMuted
                      ? selectedDayState?.expiration_state === "at_or_after_expiry"
                        ? "Expiry payoff"
                        : "No vol effect"
                      : formatSignedPercent(shift * 100, 0)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {moves.map((move) => (
                <tr key={move}>
                  <td className="px-2 py-2 text-[var(--muted-foreground)]">{formatSignedPercent(move * 100, 0)}</td>
                  {displayedShifts.map((shift) => {
                    const key = scenarioCellKey(selectedDay, move, shift);
                    const point = byCell.get(key);
                    const pnl = isFiniteNumber(point?.pnl_open) ? point.pnl_open : null;
                    const background =
                      pnl === null
                        ? "transparent"
                        : pnl > 0
                          ? `rgba(80,227,164,${Math.min(Math.abs(pnl) / 1000, 0.35)})`
                          : `rgba(255,106,117,${Math.min(Math.abs(pnl) / 1000, 0.35)})`;
                    return (
                      <td
                        key={key}
                        className="px-2 py-2 text-center"
                        data-scenario-key={key}
                        style={{ background }}
                      >
                        {formatPrice(pnl)}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
