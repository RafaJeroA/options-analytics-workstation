"use client";

import * as TabsPrimitive from "@radix-ui/react-tabs";

import { cn } from "@/lib/utils";

export const Tabs = TabsPrimitive.Root;

export function TabsList({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.List>) {
  return (
    <TabsPrimitive.List
      className={cn("inline-flex h-10 items-center gap-1 rounded-lg bg-[var(--panel-strong)] p-1", className)}
      {...props}
    />
  );
}

export function TabsTrigger({ className, ...props }: React.ComponentProps<typeof TabsPrimitive.Trigger>) {
  return (
    <TabsPrimitive.Trigger
      className={cn(
        "rounded-md px-3 py-1.5 text-sm text-[var(--muted-foreground)] outline-none transition-colors data-[state=active]:bg-[var(--panel)] data-[state=active]:text-[var(--foreground)]",
        className
      )}
      {...props}
    />
  );
}

export const TabsContent = TabsPrimitive.Content;

