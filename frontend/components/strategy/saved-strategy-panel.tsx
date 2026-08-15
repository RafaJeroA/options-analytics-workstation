"use client";

import { FolderOpen, Save, Trash2 } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { DataState } from "@/components/ui/data-state";
import type { SavedStrategyRecord } from "@/lib/types";

interface SavedStrategyPanelProps {
  records: SavedStrategyRecord[];
  activeStrategyId?: string;
  loading?: boolean;
  saving?: boolean;
  deletingStrategyId?: string;
  errorMessage?: string;
  operationError?: string;
  canSave?: boolean;
  onSave: () => void;
  onLoad: (record: SavedStrategyRecord) => void;
  onDelete: (strategyId: string) => void;
  onRetry: () => void;
}

export function SavedStrategyPanel({
  records,
  activeStrategyId,
  loading = false,
  saving = false,
  deletingStrategyId,
  errorMessage,
  operationError,
  canSave = false,
  onSave,
  onLoad,
  onDelete,
  onRetry,
}: SavedStrategyPanelProps) {
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Saved Strategies</CardTitle>
          <div className="mt-1 text-xs text-[var(--muted-foreground)]">Local workspace persistence</div>
        </div>
        <Button size="sm" disabled={!canSave || saving} onClick={onSave}>
          <Save className="size-4" />
          {saving ? "Saving..." : activeStrategyId ? "Update" : "Save"}
        </Button>
      </CardHeader>
      <CardContent>
        {operationError ? (
          <div className="mb-2 rounded-xl border border-[var(--panel-border)] bg-[var(--panel)] p-2 text-xs text-[var(--warning)]">
            {operationError}
          </div>
        ) : null}
        {loading && !records.length ? (
          <DataState message="Loading saved strategies..." tone="loading" />
        ) : errorMessage && !records.length ? (
          <DataState message={errorMessage} tone="warning" actionLabel="Retry" onAction={onRetry} />
        ) : records.length ? (
          <div className="max-h-32 space-y-2 overflow-auto">
            {records.map((record) => (
              <div
                className={`flex items-center justify-between gap-2 rounded-xl border p-2 ${
                  record.strategy_id === activeStrategyId
                    ? "border-[var(--accent)] bg-[rgba(110,231,183,0.08)]"
                    : "border-[var(--panel-border)] bg-[var(--panel-strong)]"
                }`}
                key={record.strategy_id}
              >
                <div className="min-w-0">
                  <div className="truncate text-sm font-medium">{record.name}</div>
                  <div className="text-xs text-[var(--muted-foreground)]">
                    {record.strategy.underlying_symbol} · {record.strategy.legs.length} legs
                  </div>
                </div>
                <div className="flex gap-1">
                  <Button
                    aria-label={`Load ${record.name}`}
                    size="icon"
                    variant="ghost"
                    onClick={() => onLoad(record)}
                  >
                    <FolderOpen className="size-4" />
                  </Button>
                  <Button
                    aria-label={`Delete ${record.name}`}
                    size="icon"
                    variant="ghost"
                    disabled={deletingStrategyId === record.strategy_id}
                    onClick={() => onDelete(record.strategy_id)}
                  >
                    <Trash2 className="size-4" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-xs text-[var(--muted-foreground)]">No saved strategies yet.</div>
        )}
      </CardContent>
    </Card>
  );
}
