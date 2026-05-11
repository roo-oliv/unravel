"use client";

import { useEffect, useRef } from "react";

import { cn } from "@/lib/utils";
import type { Walkthrough } from "./types";

interface Props {
  walkthrough: Walkthrough;
  activeIndex: number;
  onSelect: (index: number) => void;
  collapsed?: boolean;
}

export function ThreadList({
  walkthrough,
  activeIndex,
  onSelect,
  collapsed = false,
}: Props) {
  const order = walkthrough.suggested_order.length
    ? walkthrough.suggested_order
    : walkthrough.threads.map((t) => t.id);

  const threadsById = Object.fromEntries(
    walkthrough.threads.map((t) => [t.id, t]),
  );

  // Refs for active-row scroll-into-view on keyboard nav.
  const navRef = useRef<HTMLElement | null>(null);
  const rowRefs = useRef<Map<number, HTMLLIElement | null>>(new Map());
  const overviewRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const el =
      activeIndex === -1
        ? overviewRef.current
        : rowRefs.current.get(activeIndex);
    if (!el) return;
    el.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [activeIndex]);

  if (collapsed) {
    return (
      <nav
        ref={navRef}
        className="h-full overflow-y-auto py-2"
        aria-label="Threads"
      >
        <button
          ref={overviewRef}
          type="button"
          onClick={() => onSelect(-1)}
          title="Overview"
          aria-label="Overview"
          aria-current={activeIndex === -1 ? "true" : undefined}
          className={cn(
            "flex h-8 w-full items-center justify-center border-l-2 font-mono text-[11px] transition-colors",
            activeIndex === -1
              ? "border-foreground bg-accent text-foreground"
              : "border-transparent text-muted-foreground hover:bg-accent/60 hover:text-foreground",
          )}
        >
          00
        </button>
        <ol>
          {order.map((tid, i) => {
            const thread = threadsById[tid];
            if (!thread) return null;
            const active = activeIndex === i;
            const num = String(i + 1).padStart(2, "0");
            return (
              <li
                key={tid}
                ref={(el) => {
                  rowRefs.current.set(i, el);
                }}
              >
                <button
                  type="button"
                  onClick={() => onSelect(i)}
                  title={thread.title}
                  aria-label={`Thread ${num}: ${thread.title}`}
                  aria-current={active ? "true" : undefined}
                  className={cn(
                    "flex h-8 w-full items-center justify-center border-l-2 font-mono text-[11px] transition-colors",
                    active
                      ? "border-foreground bg-accent text-foreground"
                      : "border-transparent text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                  )}
                >
                  {num}
                </button>
              </li>
            );
          })}
        </ol>
      </nav>
    );
  }

  return (
    <nav ref={navRef} className="h-full overflow-y-auto py-3">
      <button
        ref={overviewRef}
        type="button"
        onClick={() => onSelect(-1)}
        className={cn(
          "group flex w-full items-center gap-2 border-l-2 px-3 py-2 text-left transition-colors",
          activeIndex === -1
            ? "border-foreground bg-accent text-foreground"
            : "border-transparent text-muted-foreground hover:bg-accent/60",
        )}
      >
        <span
          aria-hidden="true"
          className={cn(
            "inline-block w-3 shrink-0 text-foreground/70",
            activeIndex === -1 ? "opacity-100" : "opacity-0",
          )}
        >
          ›
        </span>
        <span className="shrink-0 text-xs font-mono text-muted-foreground">
          00
        </span>
        <span className="text-xs font-medium uppercase tracking-wide">
          Overview
        </span>
      </button>
      <ol className="mt-2">
        {order.map((tid, i) => {
          const thread = threadsById[tid];
          if (!thread) return null;
          const active = activeIndex === i;
          return (
            <li
              key={tid}
              ref={(el) => {
                rowRefs.current.set(i, el);
              }}
            >
              <button
                type="button"
                onClick={() => onSelect(i)}
                className={cn(
                  "group flex w-full items-start gap-2 border-l-2 px-3 py-3 text-left transition-colors",
                  active
                    ? "border-foreground bg-accent"
                    : "border-transparent hover:bg-accent/60",
                )}
                aria-current={active ? "true" : undefined}
              >
                <span
                  aria-hidden="true"
                  className={cn(
                    "mt-[2px] inline-block w-3 shrink-0 text-foreground/70 transition-opacity",
                    active ? "opacity-100" : "opacity-0",
                  )}
                >
                  ›
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline gap-2">
                    <span className="shrink-0 text-xs font-mono text-muted-foreground">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="text-sm font-medium leading-tight">
                      {thread.title}
                    </span>
                  </div>
                  {thread.dependencies.length > 0 && (
                    <div className="mt-1 ml-6 flex flex-wrap gap-1">
                      {thread.dependencies.map((dep) => (
                        <span
                          key={dep}
                          className="inline-flex items-center rounded bg-muted px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground"
                        >
                          ↳ {dep}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </button>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
