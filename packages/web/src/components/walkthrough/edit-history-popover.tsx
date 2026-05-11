"use client";

import { Clock, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

import type { FieldEditDTO } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  history: FieldEditDTO[];
  className?: string;
  /**
   * If true the clock is rendered yellow/orange — used by the parent when there
   * are unsaved pending edits adjacent to the saved history.
   */
  highlight?: boolean;
}

const DT_FMT = new Intl.DateTimeFormat(undefined, {
  dateStyle: "short",
  timeStyle: "short",
});

export function EditHistoryPopover({ history, className, highlight }: Props) {
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onMouseDown = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  if (history.length === 0) return null;

  return (
    <div ref={rootRef} className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-label="Show edit history"
        title={`${history.length} previous edit${history.length === 1 ? "" : "s"}`}
        className={cn(
          "rounded p-0.5 text-muted-foreground transition-colors",
          "hover:bg-accent hover:text-foreground",
          highlight && "text-amber-500 hover:text-amber-600",
        )}
      >
        <Clock className="size-3" aria-hidden="true" />
      </button>
      {open && (
        <div
          role="dialog"
          aria-label="Edit history"
          className={cn(
            "absolute right-0 top-6 z-50 w-80 rounded-lg border bg-popover p-2 shadow-md",
          )}
        >
          <header className="mb-2 flex items-center justify-between border-b pb-1.5">
            <span className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
              History · {history.length}
            </span>
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
              aria-label="Close history"
            >
              <X className="size-3" aria-hidden="true" />
            </button>
          </header>
          <ol className="max-h-72 space-y-2 overflow-y-auto">
            {history.map((edit) => (
              <li key={edit.id} className="text-xs">
                <div className="flex items-baseline justify-between gap-2 text-[10px] text-muted-foreground">
                  <span className="truncate font-mono">{edit.editor}</span>
                  <span className="tabular-nums">
                    {edit.created_at
                      ? DT_FMT.format(new Date(edit.created_at))
                      : "—"}
                  </span>
                </div>
                <div className="mt-1 space-y-0.5">
                  <div className="rounded bg-red-500/10 px-1.5 py-0.5 font-mono text-[11px] line-through opacity-80">
                    {edit.old_value || <span className="italic">(empty)</span>}
                  </div>
                  <div className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[11px]">
                    {edit.new_value || <span className="italic">(empty)</span>}
                  </div>
                </div>
              </li>
            ))}
          </ol>
        </div>
      )}
    </div>
  );
}
