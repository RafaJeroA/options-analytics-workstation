"use client";

import { useQuery } from "@tanstack/react-query";
import { Plus, Search, Star } from "lucide-react";
import { startTransition, useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";
import { useDebouncedValue } from "@/hooks/use-debounced-value";
import { api } from "@/lib/api";
import type { UnderlyingSearchResult } from "@/lib/types";

interface SidebarProps {
  currentSymbol: string;
  watchlistSymbols: string[];
  onSelectSymbol: (symbol: string) => void;
  onAddWatchlist: (symbol: string) => void;
}

function SearchResultRow({
  result,
  onSelect,
  onAddWatchlist,
}: {
  result: UnderlyingSearchResult;
  onSelect: (symbol: string) => void;
  onAddWatchlist: (symbol: string) => void;
}) {
  return (
    <div className="grid grid-cols-[1fr_auto] items-center gap-2 rounded-lg border border-transparent px-2 py-2 hover:border-[var(--panel-border)] hover:bg-[var(--panel-hover)]">
      <button className="text-left" onClick={() => onSelect(result.symbol)} type="button">
        <div className="text-sm font-semibold text-[var(--foreground)]">{result.symbol}</div>
        <div className="text-xs text-[var(--muted-foreground)]">{result.description}</div>
      </button>
      <Button size="icon" variant="ghost" onClick={() => onAddWatchlist(result.symbol)}>
        <Plus className="size-4" />
      </Button>
    </div>
  );
}

export function Sidebar({ currentSymbol, watchlistSymbols, onSelectSymbol, onAddWatchlist }: SidebarProps) {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query.trim(), 250);

  const searchQuery = useQuery({
    queryKey: ["search", debouncedQuery],
    queryFn: () => api.searchUnderlyings(debouncedQuery),
    enabled: debouncedQuery.length > 0,
    staleTime: 30_000,
  });

  return (
    <div className="panel-surface flex h-full flex-col rounded-2xl p-3">
      <Card className="border-none bg-transparent shadow-none">
        <CardHeader className="px-0 pb-2 pt-0">
          <CardTitle>Workspace</CardTitle>
        </CardHeader>
        <CardContent className="px-0 pb-0">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
            <Input
              className="pl-9"
              placeholder="Search ticker or contract"
              value={query}
              onChange={(event) => setQuery(event.target.value)}
            />
          </div>
        </CardContent>
      </Card>

      <Separator className="my-3" />

      <div className="mb-2 flex items-center justify-between">
        <div>
          <div className="metric-label">Watchlist</div>
          <div className="text-xs text-[var(--muted-foreground)]">Pinned local symbols</div>
        </div>
      </div>

      <div className="mb-3 grid gap-1">
        {watchlistSymbols.map((symbol) => (
          <button
            key={symbol}
            type="button"
            className={`flex items-center justify-between rounded-lg px-2 py-2 text-left text-sm transition-colors ${
              currentSymbol === symbol
                ? "bg-[var(--panel-hover)] text-[var(--foreground)]"
                : "text-[var(--muted-foreground)] hover:bg-[var(--panel-hover)] hover:text-[var(--foreground)]"
            }`}
            onClick={() => {
              startTransition(() => onSelectSymbol(symbol));
            }}
          >
            <span>{symbol}</span>
            <Star className={`size-3.5 ${currentSymbol === symbol ? "fill-current" : ""}`} />
          </button>
        ))}
      </div>

      <Separator className="mb-3" />

      <div className="mb-2">
        <div className="metric-label">Search Results</div>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="grid gap-1 pr-2">
          {searchQuery.data?.map((result) => (
            <SearchResultRow
              key={result.symbol}
              result={result}
              onSelect={(symbol) => {
                startTransition(() => onSelectSymbol(symbol));
              }}
              onAddWatchlist={onAddWatchlist}
            />
          ))}
          {query.length > 0 && searchQuery.isFetching ? (
            <div className="rounded-lg border border-dashed border-[var(--panel-border)] p-3 text-xs text-[var(--muted-foreground)]">
              Searching symbols...
            </div>
          ) : null}
          {query.length > 0 && !searchQuery.data?.length && !searchQuery.isFetching ? (
            <div className="rounded-lg border border-dashed border-[var(--panel-border)] p-3 text-xs text-[var(--muted-foreground)]">
              No symbols matched the current query.
            </div>
          ) : null}
        </div>
      </ScrollArea>
    </div>
  );
}
