import * as React from "react";

import { cn } from "@/lib/utils";

export function Badge({ className, ...props }: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-full border border-[var(--panel-border)] bg-[var(--panel-strong)] px-2 py-0.5 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]",
        className
      )}
      {...props}
    />
  );
}

