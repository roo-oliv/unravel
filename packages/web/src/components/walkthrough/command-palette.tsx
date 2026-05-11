"use client";

import { Command } from "cmdk";
import { useMemo } from "react";

import { cn } from "@/lib/utils";
import type { Walkthrough } from "./types";

interface Props {
  walkthrough: Walkthrough;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (index: number) => void;
}

const itemClass = cn(
  "flex cursor-pointer items-start gap-3 rounded-md px-3 py-2 text-sm",
  "data-[selected=true]:bg-accent data-[selected=true]:text-accent-foreground",
);

const groupClass = cn(
  "[&_[cmdk-group-heading]]:px-3 [&_[cmdk-group-heading]]:py-1.5",
  "[&_[cmdk-group-heading]]:text-[10px] [&_[cmdk-group-heading]]:font-medium",
  "[&_[cmdk-group-heading]]:uppercase [&_[cmdk-group-heading]]:tracking-wider",
  "[&_[cmdk-group-heading]]:text-muted-foreground",
);

export function CommandPalette({
  walkthrough,
  open,
  onOpenChange,
  onSelect,
}: Props) {
  const order = useMemo(
    () =>
      walkthrough.suggested_order.length
        ? walkthrough.suggested_order
        : walkthrough.threads.map((t) => t.id),
    [walkthrough],
  );

  const threadsById = useMemo(
    () => Object.fromEntries(walkthrough.threads.map((t) => [t.id, t])),
    [walkthrough.threads],
  );

  const choose = (index: number) => {
    onSelect(index);
    onOpenChange(false);
  };

  return (
    <Command.Dialog
      open={open}
      onOpenChange={onOpenChange}
      label="Command palette"
      shouldFilter
      loop
      className="flex flex-col overflow-hidden"
      overlayClassName="fixed inset-0 z-40 bg-background/70 backdrop-blur-sm"
      contentClassName={cn(
        "fixed left-1/2 top-[12vh] z-50 w-[92vw] max-w-xl -translate-x-1/2",
        "rounded-xl border bg-popover text-popover-foreground shadow-2xl",
        "focus:outline-none",
      )}
    >
      <div className="flex items-center gap-3 border-b px-4">
        <span
          className="select-none text-[10px] font-mono uppercase tracking-wider text-muted-foreground"
          aria-hidden="true"
        >
          ⌘K
        </span>
        <Command.Input
          placeholder="Jump to thread, search by title or summary…"
          className="h-12 w-full bg-transparent text-sm outline-none placeholder:text-muted-foreground"
        />
      </div>

      <Command.List className="max-h-[60vh] overflow-y-auto px-1 py-2">
        <Command.Empty className="px-3 py-6 text-center text-sm text-muted-foreground">
          No matches.
        </Command.Empty>

        <Command.Group heading="Navigation" className={groupClass}>
          <Command.Item
            value="overview walkthrough summary suggested order"
            onSelect={() => choose(-1)}
            className={itemClass}
          >
            <span className="w-7 shrink-0 self-center text-xs font-mono text-muted-foreground">
              ··
            </span>
            <span className="min-w-0 flex-1 self-center font-medium">
              Overview
            </span>
            <span className="ml-2 shrink-0 self-center text-[10px] text-muted-foreground">
              summary
            </span>
          </Command.Item>
        </Command.Group>

        <Command.Group
          heading={`Threads (${order.length})`}
          className={groupClass}
        >
          {order.map((tid, i) => {
            const thread = threadsById[tid];
            if (!thread) return null;
            const num = String(i + 1).padStart(2, "0");
            const value = `${num} ${thread.title} ${tid} ${thread.summary}`;
            return (
              <Command.Item
                key={tid}
                value={value}
                onSelect={() => choose(i)}
                className={itemClass}
              >
                <span className="w-7 shrink-0 pt-0.5 text-xs font-mono text-muted-foreground">
                  {num}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="truncate font-medium">{thread.title}</div>
                  {thread.summary && (
                    <div className="mt-0.5 line-clamp-1 text-xs text-muted-foreground">
                      {thread.summary}
                    </div>
                  )}
                </div>
                {thread.dependencies.length > 0 && (
                  <span className="ml-2 shrink-0 self-center rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">
                    ↳ {thread.dependencies.length}
                  </span>
                )}
              </Command.Item>
            );
          })}
        </Command.Group>
      </Command.List>

      <div className="flex items-center justify-between gap-3 border-t px-3 py-2 text-[10px] text-muted-foreground">
        <div className="flex items-center gap-2">
          <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono">
            ↑↓
          </kbd>
          <span>navigate</span>
          <kbd className="ml-2 rounded border bg-muted px-1.5 py-0.5 font-mono">
            ↵
          </kbd>
          <span>jump</span>
        </div>
        <div className="flex items-center gap-2">
          <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono">
            esc
          </kbd>
          <span>close</span>
        </div>
      </div>
    </Command.Dialog>
  );
}
