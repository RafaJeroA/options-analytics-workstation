"use client";

import { Input } from "@/components/ui/input";
import type { ChainFilters } from "@/lib/chain";

interface ChainFiltersProps {
  expirations: string[];
  selectedExpiration?: string;
  filters: ChainFilters;
  onSelectExpiration: (expiration?: string) => void;
  onUpdateFilters: (partial: Partial<ChainFilters>) => void;
}

const selectClassName =
  "h-9 rounded-md border border-[var(--panel-border)] bg-[var(--panel-strong)] px-3 text-sm text-[var(--foreground)] outline-none";

export function ChainFilters({
  expirations,
  selectedExpiration,
  filters,
  onSelectExpiration,
  onUpdateFilters,
}: ChainFiltersProps) {
  return (
    <div className="grid gap-2 rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)] p-3 xl:grid-cols-[repeat(8,minmax(0,1fr))]">
      <label className="grid gap-1">
        <span className="metric-label">Expiration</span>
        <select
          className={selectClassName}
          value={selectedExpiration ?? ""}
          onChange={(event) => onSelectExpiration(event.target.value || undefined)}
        >
          {expirations.map((expiration) => (
            <option key={expiration} value={expiration}>
              {expiration}
            </option>
          ))}
        </select>
      </label>
      <label className="grid gap-1">
        <span className="metric-label">Moneyness %</span>
        <Input
          type="number"
          value={filters.maxAbsMoneynessPct}
          onChange={(event) => onUpdateFilters({ maxAbsMoneynessPct: Number(event.target.value) })}
        />
      </label>
      <label className="grid gap-1">
        <span className="metric-label">Delta Min</span>
        <Input
          type="number"
          step="0.05"
          value={filters.deltaMin}
          onChange={(event) => onUpdateFilters({ deltaMin: Number(event.target.value) })}
        />
      </label>
      <label className="grid gap-1">
        <span className="metric-label">Delta Max</span>
        <Input
          type="number"
          step="0.05"
          value={filters.deltaMax}
          onChange={(event) => onUpdateFilters({ deltaMax: Number(event.target.value) })}
        />
      </label>
      <label className="grid gap-1">
        <span className="metric-label">IV Min</span>
        <Input
          type="number"
          step="0.05"
          value={filters.ivMin}
          onChange={(event) => onUpdateFilters({ ivMin: Number(event.target.value) })}
        />
      </label>
      <label className="grid gap-1">
        <span className="metric-label">IV Max</span>
        <Input
          type="number"
          step="0.05"
          value={filters.ivMax}
          onChange={(event) => onUpdateFilters({ ivMax: Number(event.target.value) })}
        />
      </label>
      <label className="grid gap-1">
        <span className="metric-label">Min Volume</span>
        <Input
          type="number"
          value={filters.minVolume}
          onChange={(event) => onUpdateFilters({ minVolume: Number(event.target.value) })}
        />
      </label>
      <label className="grid gap-1">
        <span className="metric-label">Min OI</span>
        <Input
          type="number"
          value={filters.minOpenInterest}
          onChange={(event) => onUpdateFilters({ minOpenInterest: Number(event.target.value) })}
        />
      </label>
      <label className="grid gap-1">
        <span className="metric-label">Max Spread %</span>
        <Input
          type="number"
          step="0.01"
          value={filters.maxSpreadPct}
          onChange={(event) => onUpdateFilters({ maxSpreadPct: Number(event.target.value) })}
        />
      </label>
      <label className="grid gap-1">
        <span className="metric-label">Sort By</span>
        <select
          className={selectClassName}
          value={filters.sortBy}
          onChange={(event) => onUpdateFilters({ sortBy: event.target.value as ChainFilters["sortBy"] })}
        >
          <option value="strike">Strike</option>
          <option value="callIv">Call IV</option>
          <option value="putIv">Put IV</option>
          <option value="callDelta">Call Delta</option>
          <option value="putDelta">Put Delta</option>
        </select>
      </label>
      <label className="grid gap-1">
        <span className="metric-label">Direction</span>
        <select
          className={selectClassName}
          value={filters.sortDirection}
          onChange={(event) => onUpdateFilters({ sortDirection: event.target.value as ChainFilters["sortDirection"] })}
        >
          <option value="asc">Ascending</option>
          <option value="desc">Descending</option>
        </select>
      </label>
    </div>
  );
}

