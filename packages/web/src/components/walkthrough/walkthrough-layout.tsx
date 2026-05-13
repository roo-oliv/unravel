"use client";

import { useQuery } from "@tanstack/react-query";
import { PanelLeftClose, PanelLeftOpen, Settings } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useHotkeys } from "react-hotkeys-hook";

import { api, type FieldEditDTO, type HunkDTO } from "@/lib/api";
import { ownsLine } from "@/lib/hunk-ownership";
import type { PendingReviewComment } from "@/lib/pending-review";
import { useMe } from "@/lib/use-me";
import { useViewedHunksStore } from "@/lib/viewed-hunks";

import { UserMenu } from "../user-menu";
import { CommandPalette } from "./command-palette";
import { PendingEditsBar } from "./pending-edits-bar";
import { PendingReviewBar } from "./pending-review-bar";
import { PrStatusBadge } from "./pr-status-badge";
import { SettingsDialog } from "./settings-dialog";
import { ShortcutsHelp } from "./shortcuts-help";
import { ThreadList } from "./thread-list";
import { ThreadStage } from "./thread-stage";
import { hunkRefs, indexHunks, type Walkthrough } from "./types";

interface Props {
  walkthrough: Walkthrough;
  slug?: string;
}

function historyKeyFor(edit: FieldEditDTO): string {
  return `${edit.target_kind}:${edit.target_id}:${edit.field}`;
}

function gridColumnsFor(opts: { sidebarCollapsed: boolean }): string {
  return `${opts.sidebarCollapsed ? "3rem" : "280px"} 1fr`;
}

export function WalkthroughLayout({ walkthrough, slug }: Props) {
  const order = walkthrough.suggested_order.length
    ? walkthrough.suggested_order
    : walkthrough.threads.map((t) => t.id);

  // -1 = overview, 0..n-1 = thread by suggested_order position
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  // Counters increment on each press; HunkView reacts on change.
  const [collapseSignal, setCollapseSignal] = useState(0);
  const [expandSignal, setExpandSignal] = useState(0);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  const hunkIndex = useMemo(() => indexHunks(walkthrough), [walkthrough]);

  const diffTotals = useMemo(() => {
    let additions = 0;
    let deletions = 0;
    for (const h of Object.values(hunkIndex)) {
      additions += h.additions || 0;
      deletions += h.deletions || 0;
    }
    return { additions, deletions };
  }, [hunkIndex]);

  // For each thread (by suggested-order index) build a file-path → hunks map.
  // Used to figure out which thread owns a pending review draft so clicking a
  // draft in the bar can switch threads before scrolling.
  const hunksByFileByThread = useMemo<Record<string, HunkDTO[]>[]>(() => {
    return order.map((tid) => {
      const thread = walkthrough.threads.find((t) => t.id === tid);
      const map: Record<string, HunkDTO[]> = {};
      if (!thread) return map;
      for (const step of thread.steps) {
        for (const ref of hunkRefs(step)) {
          const h = hunkIndex[ref];
          if (!h?.file_path) continue;
          (map[h.file_path] ??= []).push(h);
        }
      }
      return map;
    });
  }, [order, walkthrough.threads, hunkIndex]);

  const findThreadIndexFor = useCallback(
    (draft: PendingReviewComment): number | null => {
      // Prefer the current thread when it owns the draft (so a same-thread
      // click doesn't pointlessly re-navigate).
      const checkAt = (idx: number): boolean => {
        const byFile = hunksByFileByThread[idx];
        const siblings = byFile?.[draft.path];
        if (!siblings || siblings.length === 0) return false;
        return siblings.some((h) => ownsLine(h, siblings, draft.line));
      };
      if (activeIndex >= 0 && checkAt(activeIndex)) return activeIndex;
      for (let i = 0; i < hunksByFileByThread.length; i++) {
        if (i === activeIndex) continue;
        if (checkAt(i)) return i;
      }
      return null;
    },
    [hunksByFileByThread, activeIndex],
  );

  const handleRevealPending = useCallback(
    (draft: PendingReviewComment) => {
      const targetIdx = findThreadIndexFor(draft);
      const needsNav = targetIdx != null && targetIdx !== activeIndex;
      if (needsNav) setActiveIndex(targetIdx!);

      const targetDomId = `pending-draft-${draft.id}`;
      const flash = (el: HTMLElement) => {
        el.scrollIntoView({ behavior: "smooth", block: "center" });
        el.classList.add(
          "ring-2",
          "ring-amber-400",
          "ring-offset-2",
          "ring-offset-background",
        );
        setTimeout(
          () =>
            el.classList.remove(
              "ring-2",
              "ring-amber-400",
              "ring-offset-2",
              "ring-offset-background",
            ),
          1600,
        );
      };
      const dispatchAndScroll = () => {
        // Tell any HunkView hosting this draft to expand itself, then scroll.
        document.dispatchEvent(
          new CustomEvent("unravel:reveal-pending", {
            detail: { id: draft.id },
          }),
        );
        const tryScroll = (attempt: number) => {
          const el = document.getElementById(targetDomId);
          if (el) {
            flash(el);
            return;
          }
          if (attempt > 0) {
            requestAnimationFrame(() => tryScroll(attempt - 1));
          }
        };
        // A few retries cover: hunk collapsed → expanding, thread just
        // switched → ThreadStage mounting + Shiki tokenising.
        tryScroll(8);
      };
      if (needsNav) {
        // Let React commit the new thread + its hunks before reaching for the
        // DOM node. requestAnimationFrame inside dispatchAndScroll then keeps
        // polling until Shiki finishes tokenising the hunk.
        setTimeout(dispatchAndScroll, 30);
      } else {
        dispatchAndScroll();
      }
    },
    [activeIndex, findThreadIndexFor],
  );

  // Edit history (per-field popovers). Server-side append-only log; we group
  // it client-side by editKey so each EditableField gets just its own entries.
  const walkthroughUuid = walkthrough.uuid;
  const historyQuery = useQuery({
    queryKey: ["edit-history", walkthroughUuid],
    queryFn: () => api.getEditHistory(walkthroughUuid!),
    enabled: !!walkthroughUuid,
    refetchInterval: false,
  });

  // Hydrate the per-user "viewed hunks" store from the server. Anonymous /
  // dev users get an empty set (the endpoint returns []), which keeps the
  // checkboxes hidden via the same gate that controls the inline composer.
  const me = useMe().data ?? null;
  const viewedEnabled = !!me && !me.is_dev_user && !!slug;
  const hydrateViewed = useViewedHunksStore((s) => s.hydrate);
  const viewedQuery = useQuery({
    queryKey: ["viewed-hunks", slug],
    queryFn: () => api.listViewedHunks(slug!),
    enabled: viewedEnabled,
    refetchInterval: false,
  });
  useEffect(() => {
    if (!slug) return;
    hydrateViewed(slug, viewedQuery.data?.viewed_content_hashes ?? []);
  }, [slug, viewedQuery.data, hydrateViewed]);

  const viewedHashes = useViewedHunksStore(
    (s) => (slug ? s.bySlug[slug] : undefined),
  );

  // For each thread (by suggested-order index) pre-compute its total hunk
  // count and how many are viewed. Counts are deduped by content_hash so the
  // sidepanel doesn't double-count hunks reused across steps.
  const threadViewCounts = useMemo<
    Record<string, { total: number; viewed: number }>
  >(() => {
    const out: Record<string, { total: number; viewed: number }> = {};
    for (const thread of walkthrough.threads) {
      const hashes = new Set<string>();
      for (const step of thread.steps) {
        for (const ref of hunkRefs(step)) {
          const h = hunkIndex[ref];
          if (h?.content_hash) hashes.add(h.content_hash);
        }
      }
      let viewed = 0;
      if (viewedHashes) {
        for (const h of hashes) if (viewedHashes.has(h)) viewed++;
      }
      out[thread.id] = { total: hashes.size, viewed };
    }
    return out;
  }, [walkthrough.threads, hunkIndex, viewedHashes]);
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
  // ``d`` keeps a useful job in the new inline-comments world: jump straight
  // to the PR conversation feed in Overview. Inline comments in thread view
  // are always rendered so the binding is a no-op there.
  useHotkeys("d", (e) => {
    e.preventDefault();
    if (activeIndex < 0) {
      document
        .getElementById("pr-conversation")
        ?.scrollIntoView({ behavior: "smooth" });
    }
  });

  const position =
    activeIndex === -1
      ? "Overview"
      : `${String(activeIndex + 1).padStart(2, "0")} / ${String(order.length).padStart(2, "0")}`;

  return (
    <div className="h-screen grid grid-rows-[2.25rem_auto_auto_1fr_1.75rem] overflow-hidden">
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
          {walkthrough.pr && activeIndex < 0 && (
            <button
              type="button"
              onClick={() =>
                document
                  .getElementById("pr-conversation")
                  ?.scrollIntoView({ behavior: "smooth" })
              }
              className="flex items-center gap-1.5 rounded px-1.5 py-0.5 hover:bg-accent hover:text-foreground"
              title="Scroll to PR comments (d)"
            >
              <kbd className="rounded border bg-background px-1 font-mono text-[10px]">
                d
              </kbd>
              <span className="hidden sm:inline">conversation</span>
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
          <button
            type="button"
            onClick={() => setSettingsOpen(true)}
            aria-label="Display settings"
            title="Display settings"
            className="flex items-center gap-1.5 rounded px-1.5 py-0.5 hover:bg-accent hover:text-foreground"
          >
            <Settings className="size-3.5" aria-hidden="true" />
          </button>
          <div className="ml-2 border-l pl-2">
            <UserMenu next={slug ? `/walkthrough/${slug}` : "/repos"} />
          </div>
        </div>
      </header>

      {walkthroughUuid && walkthrough.pr && (
        <div className="row-start-2">
          <PendingReviewBar
            walkthroughUuid={walkthroughUuid}
            additions={diffTotals.additions}
            deletions={diffTotals.deletions}
            onRevealPending={handleRevealPending}
          />
        </div>
      )}

      {walkthroughUuid && (
        <div className="row-start-3">
          <PendingEditsBar walkthroughUuid={walkthroughUuid} slug={slug} />
        </div>
      )}

      <div
        className="row-start-4 grid overflow-hidden transition-[grid-template-columns] duration-150"
        style={{
          gridTemplateColumns: gridColumnsFor({ sidebarCollapsed }),
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
            threadViewCounts={threadViewCounts}
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
      </div>

      <footer className="row-start-5 flex items-center justify-between gap-4 border-t bg-muted/20 px-4 font-mono text-[10px] text-muted-foreground">
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
      />
      <ShortcutsHelp open={helpOpen} onOpenChange={setHelpOpen} />
      <SettingsDialog open={settingsOpen} onOpenChange={setSettingsOpen} />
    </div>
  );
}
