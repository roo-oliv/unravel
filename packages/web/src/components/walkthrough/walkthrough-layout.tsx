"use client";

import { useQuery } from "@tanstack/react-query";
import { PanelLeftClose, PanelLeftOpen } from "lucide-react";
import Link from "next/link";
import { useMemo, useState } from "react";
import { useHotkeys } from "react-hotkeys-hook";

import { api, type FieldEditDTO } from "@/lib/api";

import { UserMenu } from "../user-menu";
import { CommandPalette } from "./command-palette";
import { CommentsDrawer } from "./comments-drawer";
import { PendingEditsBar } from "./pending-edits-bar";
import { PrStatusBadge } from "./pr-status-badge";
import { ShortcutsHelp } from "./shortcuts-help";
import { ThreadList } from "./thread-list";
import { ThreadStage } from "./thread-stage";
import { indexHunks, type Walkthrough } from "./types";

interface Props {
  walkthrough: Walkthrough;
  slug?: string;
}

function historyKeyFor(edit: FieldEditDTO): string {
  return `${edit.target_kind}:${edit.target_id}:${edit.field}`;
}

function gridColumnsFor(opts: {
  sidebarCollapsed: boolean;
  commentsOpen: boolean;
}): string {
  const left = opts.sidebarCollapsed ? "3rem" : "280px";
  const right = opts.commentsOpen ? " 360px" : "";
  return `${left} 1fr${right}`;
}

export function WalkthroughLayout({ walkthrough, slug }: Props) {
  const order = walkthrough.suggested_order.length
    ? walkthrough.suggested_order
    : walkthrough.threads.map((t) => t.id);

  // -1 = overview, 0..n-1 = thread by suggested_order position
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  // Counters increment on each press; HunkView reacts on change.
  const [collapseSignal, setCollapseSignal] = useState(0);
  const [expandSignal, setExpandSignal] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const [commentsOpen, setCommentsOpen] = useState(false);

  const hunkIndex = useMemo(() => indexHunks(walkthrough), [walkthrough]);

  // Edit history (per-field popovers). Server-side append-only log; we group
  // it client-side by editKey so each EditableField gets just its own entries.
  const walkthroughUuid = walkthrough.uuid;
  const historyQuery = useQuery({
    queryKey: ["edit-history", walkthroughUuid],
    queryFn: () => api.getEditHistory(walkthroughUuid!),
    enabled: !!walkthroughUuid,
    refetchInterval: false,
  });
  const historyByKey = useMemo<Record<string, FieldEditDTO[]>>(() => {
    const map: Record<string, FieldEditDTO[]> = {};
    for (const edit of historyQuery.data?.history ?? []) {
      const k = historyKeyFor(edit);
      (map[k] ??= []).push(edit);
    }
    return map;
  }, [historyQuery.data]);

  const activeThread = useMemo(() => {
    if (activeIndex < 0) return null;
    const tid = order[activeIndex];
    return walkthrough.threads.find((t) => t.id === tid) ?? null;
  }, [activeIndex, order, walkthrough.threads]);

  // When a thread is active, scope inline review comments to whichever file
  // path the first hunk touches. Coarse but useful — line-level mapping
  // requires resolving each hunk's range against the comment's anchor line.
  const activeFilterPath = useMemo<string | null>(() => {
    if (!activeThread) return null;
    for (const step of activeThread.steps) {
      for (const ref of step.hunks) {
        if (typeof ref === "string") {
          const h = hunkIndex[ref];
          if (h?.file_path) return h.file_path;
        } else if (ref.file_path) {
          return ref.file_path;
        }
      }
    }
    return null;
  }, [activeThread, hunkIndex]);

  // TUI parity bindings.
  useHotkeys("tab", (e) => {
    e.preventDefault();
    setActiveIndex((i) => Math.min(order.length - 1, i + 1));
  });
  useHotkeys("shift+tab", (e) => {
    e.preventDefault();
    setActiveIndex((i) => Math.max(-1, i - 1));
  });
  useHotkeys("j,right", (e) => {
    e.preventDefault();
    setActiveIndex((i) => Math.min(order.length - 1, i + 1));
  });
  useHotkeys("k,left", (e) => {
    e.preventDefault();
    setActiveIndex((i) => Math.max(-1, i - 1));
  });
  useHotkeys(
    "mod+k",
    (e) => {
      e.preventDefault();
      setPaletteOpen((o) => !o);
    },
    { enableOnFormTags: true, enableOnContentEditable: true },
  );
  useHotkeys("h", (e) => {
    e.preventDefault();
    setHelpOpen((o) => !o);
  });
  useHotkeys("e", (e) => {
    e.preventDefault();
    setExpandSignal((n) => n + 1);
  });
  useHotkeys("c", (e) => {
    e.preventDefault();
    setCollapseSignal((n) => n + 1);
  });
  useHotkeys("f", (e) => {
    e.preventDefault();
    setSidebarCollapsed((c) => !c);
  });
  useHotkeys("d", (e) => {
    e.preventDefault();
    setCommentsOpen((c) => !c);
  });

  const position =
    activeIndex === -1
      ? "Overview"
      : `${String(activeIndex + 1).padStart(2, "0")} / ${String(order.length).padStart(2, "0")}`;

  return (
    <div className="h-screen grid grid-rows-[2.25rem_auto_1fr_1.75rem] overflow-hidden">
      {/* Each slot pins its grid-row explicitly so the layout stays put when */}
      {/* PendingEditsBar renders null (no pending edits) — without this, */}
      {/* auto-placement collapses the bar slot and footer absorbs the 1fr row. */}
      <header className="row-start-1 flex items-center justify-between border-b bg-muted/30 px-4 text-xs">
        <nav className="flex min-w-0 items-center gap-2 font-mono text-muted-foreground">
          <Link
            href="/repos"
            className="rounded px-1 py-0.5 hover:bg-accent hover:text-foreground"
          >
            fixtures
          </Link>
          <span aria-hidden="true">/</span>
          <span className="truncate text-foreground">{slug ?? "walkthrough"}</span>
          {walkthroughUuid && walkthrough.pr && (
            <span className="ml-2 hidden sm:inline-flex">
              <PrStatusBadge
                walkthroughUuid={walkthroughUuid}
                fallbackHref={walkthrough.pr.html_url}
              />
            </span>
          )}
        </nav>
        <div className="flex items-center gap-3 text-muted-foreground">
          {walkthrough.pr && (
            <button
              type="button"
              onClick={() => setCommentsOpen((c) => !c)}
              aria-pressed={commentsOpen}
              className="flex items-center gap-1.5 rounded px-1.5 py-0.5 hover:bg-accent hover:text-foreground"
              title="Toggle comments (d)"
            >
              <kbd className="rounded border bg-background px-1 font-mono text-[10px]">
                d
              </kbd>
              <span className="hidden sm:inline">comments</span>
            </button>
          )}
          <button
            type="button"
            onClick={() => setPaletteOpen(true)}
            className="flex items-center gap-1.5 rounded px-1.5 py-0.5 hover:bg-accent hover:text-foreground"
          >
            <kbd className="rounded border bg-background px-1 font-mono text-[10px]">
              ⌘K
            </kbd>
            <span className="hidden sm:inline">jump</span>
          </button>
          <button
            type="button"
            onClick={() => setHelpOpen(true)}
            className="flex items-center gap-1.5 rounded px-1.5 py-0.5 hover:bg-accent hover:text-foreground"
          >
            <kbd className="rounded border bg-background px-1 font-mono text-[10px]">
              h
            </kbd>
            <span className="hidden sm:inline">help</span>
          </button>
          <div className="ml-2 border-l pl-2">
            <UserMenu next={slug ? `/walkthrough/${slug}` : "/repos"} />
          </div>
        </div>
      </header>

      {walkthroughUuid && (
        <div className="row-start-2">
          <PendingEditsBar walkthroughUuid={walkthroughUuid} slug={slug} />
        </div>
      )}

      <div
        className="row-start-3 grid overflow-hidden transition-[grid-template-columns] duration-150"
        style={{
          gridTemplateColumns: gridColumnsFor({
            sidebarCollapsed,
            commentsOpen: commentsOpen && !!walkthrough.pr && !!walkthroughUuid,
          }),
        }}
      >
        <aside className="flex flex-col overflow-hidden border-r bg-muted/20">
          {sidebarCollapsed ? (
            <div className="flex h-[3.25rem] items-center justify-center border-b">
              <button
                type="button"
                onClick={() => setSidebarCollapsed(false)}
                aria-label="Expand sidebar"
                title="Expand sidebar (f)"
                className="rounded p-1.5 text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <PanelLeftOpen className="size-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-start justify-between gap-2 border-b px-4 py-3">
              <div className="min-w-0">
                <div className="text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  Walkthrough
                </div>
                <div className="mt-1 truncate text-sm font-medium">
                  {walkthrough.threads.length} threads ·{" "}
                  {Object.keys(hunkIndex).length} hunks
                </div>
              </div>
              <button
                type="button"
                onClick={() => setSidebarCollapsed(true)}
                aria-label="Collapse sidebar"
                title="Collapse sidebar (f)"
                className="shrink-0 rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
              >
                <PanelLeftClose className="size-4" />
              </button>
            </div>
          )}
          <ThreadList
            walkthrough={walkthrough}
            activeIndex={activeIndex}
            onSelect={setActiveIndex}
            collapsed={sidebarCollapsed}
          />
        </aside>
        <main className="min-h-0 overflow-hidden bg-background">
          <ThreadStage
            walkthrough={walkthrough}
            thread={activeThread}
            hunkIndex={hunkIndex}
            collapseSignal={collapseSignal}
            expandSignal={expandSignal}
            slug={slug}
            walkthroughUuid={walkthroughUuid}
            historyByKey={historyByKey}
          />
        </main>
        {walkthroughUuid && walkthrough.pr && commentsOpen && (
          <CommentsDrawer
            walkthroughUuid={walkthroughUuid}
            open={commentsOpen}
            onClose={() => setCommentsOpen(false)}
            filterPath={activeFilterPath}
          />
        )}
      </div>

      <footer className="row-start-4 flex items-center justify-between gap-4 border-t bg-muted/20 px-4 font-mono text-[10px] text-muted-foreground">
        <div className="flex min-w-0 flex-1 items-center gap-x-4 gap-y-0.5 overflow-hidden whitespace-nowrap">
          <span className="flex items-center gap-1">
            <kbd className="rounded border bg-background px-1 py-0.5">j</kbd>
            <kbd className="rounded border bg-background px-1 py-0.5">k</kbd>
            <kbd className="rounded border bg-background px-1 py-0.5">↹</kbd>
            <span className="ml-1">navigate</span>
          </span>
          <span className="flex items-center gap-1">
            <kbd className="rounded border bg-background px-1 py-0.5">e</kbd>
            <kbd className="rounded border bg-background px-1 py-0.5">c</kbd>
            <span className="ml-1">expand / collapse</span>
          </span>
          <span className="hidden items-center gap-1 sm:flex">
            <kbd className="rounded border bg-background px-1 py-0.5">f</kbd>
            <span>focus</span>
          </span>
          {walkthrough.pr && (
            <span className="hidden items-center gap-1 sm:flex">
              <kbd className="rounded border bg-background px-1 py-0.5">d</kbd>
              <span>comments</span>
            </span>
          )}
          <span className="hidden items-center gap-1 md:flex">
            <kbd className="rounded border bg-background px-1 py-0.5">⌘K</kbd>
            <span>palette</span>
          </span>
          <span className="hidden items-center gap-1 lg:flex">
            <kbd className="rounded border bg-background px-1 py-0.5">h</kbd>
            <span>help</span>
          </span>
          <span className="hidden items-center gap-1 lg:flex">
            <kbd className="rounded border bg-background px-1 py-0.5">esc</kbd>
            <span>close</span>
          </span>
        </div>
        <div className="shrink-0 tabular-nums text-foreground/80">
          {position}
        </div>
      </footer>

      <CommandPalette
        walkthrough={walkthrough}
        open={paletteOpen}
        onOpenChange={setPaletteOpen}
        onSelect={setActiveIndex}
        commentsOpen={commentsOpen}
        onToggleComments={() => setCommentsOpen((c) => !c)}
      />
      <ShortcutsHelp open={helpOpen} onOpenChange={setHelpOpen} />
    </div>
  );
}
