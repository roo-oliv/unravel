"use client";

import { ChevronDown, ChevronRight } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import { cn } from "@/lib/utils";
import {
  classifyDiff,
  highlightDiff,
  languageForPath,
  type DiffLine,
  type LineKind,
} from "@/lib/diff-highlight";
import type { Hunk } from "./types";

function lineClass(kind: LineKind): string {
  if (kind === "add") return "bg-diff-add/40 border-l-2 border-diff-addLine";
  if (kind === "del") return "bg-diff-del/40 border-l-2 border-diff-delLine";
  if (kind === "hunk") return "text-muted-foreground bg-muted/30";
  return "border-l-2 border-transparent";
}

function prefixClass(kind: LineKind): string {
  if (kind === "add") return "text-emerald-700 dark:text-emerald-400";
  if (kind === "del") return "text-rose-700 dark:text-rose-400";
  return "text-muted-foreground";
}

function fallbackLines(content: string): DiffLine[] {
  return classifyDiff(content).map((c) => ({
    kind: c.kind,
    raw: c.raw,
    prefix: c.prefix,
    tokens: [{ content: c.body, offset: 0 }],
  }));
}

interface HunkViewProps {
  hunk: Hunk;
  collapseSignal?: number;
  expandSignal?: number;
  /**
   * CSS `top` value applied to the hunk header (as `position: sticky`).
   * Pass a string like "96px" or a `calc(...)` expression. When omitted, the
   * header is not sticky.
   */
  stickyTop?: string;
}

export function HunkView({
  hunk,
  collapseSignal = 0,
  expandSignal = 0,
  stickyTop,
}: HunkViewProps) {
  const fallback = useMemo(() => fallbackLines(hunk.content), [hunk.content]);
  const [lines, setLines] = useState<DiffLine[]>(fallback);
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    if (collapseSignal === 0) return;
    setCollapsed(true);
  }, [collapseSignal]);

  useEffect(() => {
    if (expandSignal === 0) return;
    setCollapsed(false);
  }, [expandSignal]);

  useEffect(() => {
    if (languageForPath(hunk.file_path) === "text") {
      setLines(fallback);
      return;
    }
    let cancelled = false;
    highlightDiff(hunk.content, hunk.file_path).then((highlighted) => {
      if (!cancelled) setLines(highlighted);
    });
    return () => {
      cancelled = true;
    };
  }, [hunk.content, hunk.file_path, fallback]);

  const headerStyle: React.CSSProperties | undefined = stickyTop
    ? { position: "sticky", top: stickyTop, zIndex: 10 }
    : undefined;

  // The <article> uses `clip-path` (not overflow-hidden) so children — including
  // the rectangular sticky header — are clipped to the rounded card shape.
  // We can't use overflow-hidden because that would create a new scroll
  // container and break `position: sticky` on the header.
  return (
    <article
      className="rounded-lg border bg-card"
      style={{ clipPath: "inset(0 round 0.5rem)" }}
    >
      <header
        style={headerStyle}
        className={cn(
          "flex items-center gap-3 bg-muted px-3 py-2",
          !collapsed && "border-b",
        )}
      >
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          aria-label={collapsed ? "Expand hunk" : "Collapse hunk"}
          aria-expanded={!collapsed}
          className="shrink-0 rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
        >
          {collapsed ? (
            <ChevronRight className="size-3.5" />
          ) : (
            <ChevronDown className="size-3.5" />
          )}
        </button>
        <button
          type="button"
          onClick={() => setCollapsed((c) => !c)}
          className="min-w-0 flex-1 text-left"
        >
          {hunk.caption && (
            <div className="truncate text-sm font-medium">{hunk.caption}</div>
          )}
          <div className="truncate font-mono text-xs text-muted-foreground">
            {hunk.file_path}
            <span className="ml-2 opacity-70">
              @@ {hunk.old_start},{hunk.old_count} → {hunk.new_start},
              {hunk.new_count}
            </span>
          </div>
        </button>
        <div className="flex shrink-0 items-center gap-2 font-mono text-xs">
          {hunk.additions > 0 && (
            <span className="text-emerald-600 dark:text-emerald-400">
              +{hunk.additions}
            </span>
          )}
          {hunk.deletions > 0 && (
            <span className="text-rose-600 dark:text-rose-400">
              −{hunk.deletions}
            </span>
          )}
        </div>
      </header>
      {!collapsed && (
        <div className="overflow-x-auto">
          <pre className="shiki-diff font-mono text-xs leading-5">
            {lines.map((line, i) => (
              <div
                key={i}
                className={cn("flex whitespace-pre pr-3", lineClass(line.kind))}
              >
                <span
                  className={cn(
                    "w-6 shrink-0 select-none text-center",
                    prefixClass(line.kind),
                  )}
                  aria-hidden="true"
                >
                  {line.prefix || " "}
                </span>
                <span className="flex-1">
                  {line.tokens.length === 0 ? (
                    " "
                  ) : (
                    line.tokens.map((token, j) => (
                      <span
                        key={j}
                        style={
                          token.htmlStyle as React.CSSProperties | undefined
                        }
                      >
                        {token.content}
                      </span>
                    ))
                  )}
                </span>
              </div>
            ))}
          </pre>
        </div>
      )}
    </article>
  );
}
