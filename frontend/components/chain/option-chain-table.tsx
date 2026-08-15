"use client";

import { Pin, Plus, TrendingDown } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import type { ChainRow } from "@/lib/chain";
import { formatNumber, formatPercent, formatPrice, formatSignedNumber, isFiniteNumber } from "@/lib/format";
import { getStagedOptionEntryPrice } from "@/lib/strategy-pricing";
import type { OptionQuote } from "@/lib/types";

interface OptionChainTableProps {
  rows: ChainRow[];
  selectedContract?: OptionQuote;
  onSelectContract: (quote: OptionQuote) => void;
  onAddLong: (quote: OptionQuote) => void;
  onAddShort: (quote: OptionQuote) => void;
  onTogglePinned: (contractId: string) => void;
}

function rowTone(row: ChainRow) {
  const severe = row.flags.includes("crossed_market") || row.flags.includes("suspicious_mid");
  const warning = row.flags.includes("wide_spread") || row.flags.includes("invalid_for_iv");
  if (severe) return "bg-[rgba(136,24,41,0.18)]";
  if (warning) return "bg-[rgba(140,98,18,0.16)]";
  return "hover:bg-[var(--panel-hover)]";
}

function numericClass(value: number | null | undefined) {
  if (!isFiniteNumber(value)) return "text-[var(--muted-foreground)]";
  return value >= 0 ? "number-positive" : "number-negative";
}

function quoteLabel(quote?: OptionQuote) {
  return quote ? quote.data_flags.join(", ") : "";
}

export function OptionChainTable({
  rows,
  selectedContract,
  onSelectContract,
  onAddLong,
  onAddShort,
  onTogglePinned,
}: OptionChainTableProps) {
  return (
    <ScrollArea className="table-scroll min-h-0 flex-1 rounded-xl border border-[var(--panel-border)] bg-[var(--panel-strong)]">
      <table className="min-w-full border-collapse text-[11px]">
        <thead className="sticky top-0 z-10 bg-[rgba(8,12,19,0.98)] text-[var(--muted-foreground)]">
          <tr className="[&>th]:border-b [&>th]:border-[var(--panel-border)] [&>th]:px-2 [&>th]:py-2 [&>th]:font-medium [&>th]:uppercase [&>th]:tracking-[0.16em]">
            <th>Pin</th>
            <th>Call +</th>
            <th>Call -</th>
            <th>Bid</th>
            <th>Ask</th>
            <th>Mark</th>
            <th>IV</th>
            <th>Δ</th>
            <th>Vol</th>
            <th>OI</th>
            <th className="text-center text-[var(--foreground)]">Strike</th>
            <th>OI</th>
            <th>Vol</th>
            <th>Δ</th>
            <th>IV</th>
            <th>Mark</th>
            <th>Bid</th>
            <th>Ask</th>
            <th>Put +</th>
            <th>Put -</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const selected = selectedContract?.contract.contract_id;
            const callSelected = selected === row.call?.contract.contract_id;
            const putSelected = selected === row.put?.contract.contract_id;
            const call = row.call;
            const put = row.put;

            return (
              <tr
                className={`border-b border-[var(--panel-border)] ${rowTone(row)}`}
                data-strike={row.strike}
                key={row.strike}
                title={quoteLabel(row.call) || quoteLabel(row.put)}
              >
                <td className="px-2 py-1.5 text-center">
                  <button
                    className={`rounded p-1 ${row.pinned ? "text-[var(--accent)]" : "text-[var(--muted-foreground)]"}`}
                    onClick={() => onTogglePinned(call?.contract.contract_id ?? put?.contract.contract_id ?? "")}
                    type="button"
                  >
                    <Pin className={`size-3.5 ${row.pinned ? "fill-current" : ""}`} />
                  </button>
                </td>
                <td className="px-2 py-1.5 text-center">
                  {call ? (
                    <Button size="icon" variant="ghost" disabled={getStagedOptionEntryPrice(call) === undefined} onClick={() => onAddLong(call)}>
                      <Plus className="size-3.5" />
                    </Button>
                  ) : null}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {call ? (
                    <Button size="icon" variant="ghost" disabled={getStagedOptionEntryPrice(call) === undefined} onClick={() => onAddShort(call)}>
                      <TrendingDown className="size-3.5" />
                    </Button>
                  ) : null}
                </td>
                <td className="cursor-pointer px-2 py-1.5" onClick={() => call && onSelectContract(call)}>
                  {formatPrice(call?.bid)}
                </td>
                <td className="cursor-pointer px-2 py-1.5" onClick={() => call && onSelectContract(call)}>
                  {formatPrice(call?.ask)}
                </td>
                <td
                  className={`cursor-pointer px-2 py-1.5 ${callSelected ? "bg-[rgba(110,231,183,0.12)]" : ""}`}
                  data-contract-id={call?.contract.contract_id}
                  onClick={() => call && onSelectContract(call)}
                >
                  {formatPrice(call?.mark)}
                </td>
                <td className="px-2 py-1.5">{formatPercent(call?.implied_vol, 1)}</td>
                <td className={`px-2 py-1.5 ${numericClass(call?.greeks?.delta)}`}>
                  {call?.greeks?.delta !== null && call?.greeks?.delta !== undefined ? formatSignedNumber(call.greeks.delta, 3) : "--"}
                </td>
                <td className="px-2 py-1.5">{call?.volume ?? "--"}</td>
                <td className="px-2 py-1.5">{call?.open_interest ?? call?.openInterest ?? "--"}</td>
                <td className="bg-[rgba(255,255,255,0.02)] px-2 py-1.5 text-center font-semibold text-[var(--foreground)]">
                  {formatNumber(row.strike)}
                </td>
                <td className="px-2 py-1.5">{put?.open_interest ?? put?.openInterest ?? "--"}</td>
                <td className="px-2 py-1.5">{put?.volume ?? "--"}</td>
                <td className={`px-2 py-1.5 ${numericClass(put?.greeks?.delta)}`}>
                  {put?.greeks?.delta !== null && put?.greeks?.delta !== undefined ? formatSignedNumber(put.greeks.delta, 3) : "--"}
                </td>
                <td className="px-2 py-1.5">{formatPercent(put?.implied_vol, 1)}</td>
                <td
                  className={`cursor-pointer px-2 py-1.5 ${putSelected ? "bg-[rgba(110,231,183,0.12)]" : ""}`}
                  data-contract-id={put?.contract.contract_id}
                  onClick={() => put && onSelectContract(put)}
                >
                  {formatPrice(put?.mark)}
                </td>
                <td className="cursor-pointer px-2 py-1.5" onClick={() => put && onSelectContract(put)}>
                  {formatPrice(put?.bid)}
                </td>
                <td className="cursor-pointer px-2 py-1.5" onClick={() => put && onSelectContract(put)}>
                  {formatPrice(put?.ask)}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {put ? (
                    <Button size="icon" variant="ghost" disabled={getStagedOptionEntryPrice(put) === undefined} onClick={() => onAddLong(put)}>
                      <Plus className="size-3.5" />
                    </Button>
                  ) : null}
                </td>
                <td className="px-2 py-1.5 text-center">
                  {put ? (
                    <Button size="icon" variant="ghost" disabled={getStagedOptionEntryPrice(put) === undefined} onClick={() => onAddShort(put)}>
                      <TrendingDown className="size-3.5" />
                    </Button>
                  ) : null}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </ScrollArea>
  );
}
