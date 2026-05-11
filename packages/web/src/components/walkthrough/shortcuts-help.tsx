"use client";

import { useEffect } from "react";

import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

interface Shortcut {
  keys: string[];
  label: string;
}

interface Group {
  heading: string;
  items: Shortcut[];
}

const groups: Group[] = [
  {
    heading: "Navigation",
    items: [
      { keys: ["Tab"], label: "Next thread" },
      { keys: ["⇧", "Tab"], label: "Previous thread" },
      { keys: ["j"], label: "Next thread" },
      { keys: ["k"], label: "Previous thread" },
      { keys: ["→"], label: "Next thread" },
      { keys: ["←"], label: "Previous thread" },
    ],
  },
  {
    heading: "Layout & hunks",
    items: [
      { keys: ["f"], label: "Focus mode (collapse sidebar)" },
      { keys: ["e"], label: "Expand all hunks" },
      { keys: ["c"], label: "Collapse all hunks" },
    ],
  },
  {
    heading: "Palette & help",
    items: [
      { keys: ["⌘", "K"], label: "Command palette / jump to thread" },
      { keys: ["h"], label: "Toggle this help" },
      { keys: ["Esc"], label: "Close any overlay" },
    ],
  },
];

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="min-w-[1.5rem] rounded border bg-muted px-1.5 py-0.5 text-center font-mono text-[11px] leading-none">
      {children}
    </kbd>
  );
}

export function ShortcutsHelp({ open, onOpenChange }: Props) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onOpenChange(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Keyboard shortcuts"
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      <button
        type="button"
        aria-label="Close keyboard shortcuts"
        onClick={() => onOpenChange(false)}
        className="absolute inset-0 z-0 bg-background/70 backdrop-blur-sm"
      />
      <div
        className={cn(
          "relative z-10 w-[92vw] max-w-md overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-2xl",
        )}
      >
        <div className="flex items-baseline justify-between border-b px-4 py-3">
          <h2 className="text-sm font-semibold">Keyboard shortcuts</h2>
          <span className="text-[10px] font-mono uppercase tracking-wider text-muted-foreground">
            esc to close
          </span>
        </div>
        <div className="grid gap-5 px-4 py-4">
          {groups.map((group) => (
            <section key={group.heading}>
              <h3 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                {group.heading}
              </h3>
              <dl className="space-y-1.5 text-sm">
                {group.items.map((item, idx) => (
                  <div
                    key={`${item.label}-${idx}`}
                    className="flex items-center justify-between gap-3"
                  >
                    <dt>{item.label}</dt>
                    <dd className="flex shrink-0 items-center gap-1">
                      {item.keys.map((k, i) => (
                        <Kbd key={i}>{k}</Kbd>
                      ))}
                    </dd>
                  </div>
                ))}
              </dl>
            </section>
          ))}
        </div>
      </div>
    </div>
  );
}
