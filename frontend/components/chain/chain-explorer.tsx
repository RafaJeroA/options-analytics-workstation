"use client";

import { AlertTriangle } from "lucide-react";
import { useMemo } from "react";

import { ChainFilters as ChainFiltersPanel } from "@/components/chain/chain-filters";
import { OptionChainTable } from "@/components/chain/option-chain-table";
import { DataState } from "@/components/ui/data-state";
import { buildChainRows, type ChainFilters } from "@/lib/chain";
import { formatMarketDataMode } from "@/lib/format";
import type { ChainSnapshot, OptionQuote } from "@/lib/types";

interface ChainExplorerProps {
  chain?: ChainSnapshot;
  selectedContract?: OptionQuote;
  selectedExpiration?: string;
  filters: ChainFilters;
  pinnedContracts: string[];
  loading?: boolean;
  refreshing?: boolean;
  errorMessage?: string;
  retryable?: boolean;
  onRetry?: () => void;
  onSelectExpiration: (expiration?: string) => void;
  onSelectContract: (quote: OptionQuote) => void;
  onAddLong: (quote: OptionQuote) => void;
  onAddShort: (quote: OptionQuote) => void;
  onTogglePinned: (contractId: string) => void;
  onUpdateFilters: (partial: Partial<ChainFilters>) => void;
}

export function ChainExplorer({
  chain,
  selectedContract,
  selectedExpiration,
  filters,
  pinnedContracts,
  loading = false,
  refreshing = false,
  errorMessage,
  retryable = false,
  onRetry,
  onSelectExpiration,
  onSelectContract,
  onAddLong,
  onAddShort,
  onTogglePinned,
  onUpdateFilters,
}: ChainExplorerProps) {
  const rows = useMemo(() => buildChainRows(chain, filters, pinnedContracts), [chain, filters, pinnedContracts]);
  const flaggedRows = rows.filter((row) => row.flags.length > 0).length;

  if (!chain && loading) {
    return <DataState message="Loading option chain..." tone="loading" />;
  }

  if (!chain && errorMessage) {
    return (
      <DataState
        message={errorMessage}
        tone="warning"
        actionLabel={retryable ? "Retry" : undefined}
        onAction={retryable ? onRetry : undefined}
      />
    );
  }

  if (!chain) {
    return <DataState message="No option-chain data is available for this symbol." tone="warning" />;
  }

  return (
    <div className="flex h-full flex-col gap-3">
      <ChainFiltersPanel
        expirations={chain?.expirations ?? []}
        selectedExpiration={selectedExpiration}
        filters={filters}
        onSelectExpiration={onSelectExpiration}
        onUpdateFilters={onUpdateFilters}
      />
      <div className="flex items-center justify-between rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)] px-3 py-2 text-xs text-[var(--muted-foreground)]">
        <div>
          {refreshing
            ? "Refreshing active chain..."
            : `${rows.length} rows visible | ${flaggedRows} flagged | ${formatMarketDataMode(chain?.market_data_mode)}`}
        </div>
        <div className="flex items-center gap-2">
          <AlertTriangle className="size-4 text-[var(--warning)]" />
          Invalid or suspicious mids are excluded from local IV estimation.
        </div>
      </div>
      <OptionChainTable
        rows={rows}
        selectedContract={selectedContract}
        onSelectContract={onSelectContract}
        onAddLong={onAddLong}
        onAddShort={onAddShort}
        onTogglePinned={onTogglePinned}
      />
    </div>
  );
}
