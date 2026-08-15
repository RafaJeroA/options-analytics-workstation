"use client";

import { AlertTriangle, Info, LoaderCircle } from "lucide-react";

import { Button } from "@/components/ui/button";

type DataStateTone = "loading" | "warning" | "neutral";

interface DataStateProps {
  message: string;
  tone?: DataStateTone;
  actionLabel?: string;
  onAction?: () => void;
}

export function DataState({ message, tone = "neutral", actionLabel, onAction }: DataStateProps) {
  const Icon = tone === "loading" ? LoaderCircle : tone === "warning" ? AlertTriangle : Info;
  const iconClassName =
    tone === "loading"
      ? "text-[var(--accent)]"
      : tone === "warning"
        ? "text-[var(--warning)]"
        : "text-[var(--muted-foreground)]";

  return (
    <div className="flex h-full min-h-0 items-center justify-center rounded-xl border border-dashed border-[var(--panel-border)] bg-[var(--panel-strong)]/60 p-4 text-center">
      <div className="max-w-sm text-sm text-[var(--muted-foreground)]">
        <Icon className={`mx-auto mb-2 size-5 ${iconClassName} ${tone === "loading" ? "animate-spin" : ""}`} />
        <div>{message}</div>
        {actionLabel && onAction ? (
          <Button className="mt-3" size="sm" variant="secondary" onClick={onAction}>
            {actionLabel}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
