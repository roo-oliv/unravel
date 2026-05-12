"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ChevronDown,
  ChevronRight,
  ChevronsDown,
  ChevronsUp,
  ExternalLink,
  Loader2,
  Plus,
} from "lucide-react";
import type { CSSProperties } from "react";
import { useEffect, useMemo, useState } from "react";
import type { ThemedToken } from "shiki";

import { ApiError, api, type CommentDTO } from "@/lib/api";
import {
  classifyDiff,
  getDiffHighlighter,
  highlightDiff,
  languageForPath,
  LIGHT_THEME,
  DARK_THEME,
  type DiffLine,
  type LineKind,
} from "@/lib/diff-highlight";
import {
  formatDate,
  groupReviewCommentThreads,
  type CommentThread,
} from "@/lib/comment-threads";
import {
  newPendingId,
  usePendingReviewStore,
} from "@/lib/pending-review";
import { cn } from "@/lib/utils";

import { CommentComposer } from "./comment-composer";
import { Markdown } from "./markdown";
import type { Hunk } from "./types";

type LineSide = "LEFT" | "RIGHT";

interface LineSelection {
  side: LineSide;
  start: number; // line number in `side` coords
  end: number;
}

function selectableSide(row: RenderedRow): LineSide | null {
  if (row.kind === "hunk") return null;
  // Lines fetched via "Expand up/down" sit outside the PR diff that GitHub's
  // review API knows about. Both REST and GraphQL reject anchors on those
  // lines with ``Line could not be resolved`` — GitHub web sidesteps this
  // with an internal session-level diff that isn't part of the public API,
  // so we block selection there. Users can still comment on any line of the
  // original hunks (added/deleted/context).
  if (row.kind === "ctx-fetched") return null;
  if (row.kind === "del") return row.oldLine != null ? "LEFT" : null;
  return row.newLine != null ? "RIGHT" : null;
}

function lineForSide(row: RenderedRow, side: LineSide): number | null {
  return side === "LEFT" ? row.oldLine : row.newLine;
}

function isLineInSelection(
  row: RenderedRow,
  selection: LineSelection | null,
): boolean {
  if (!selection) return false;
  const line = lineForSide(row, selection.side);
  if (line == null) return false;
  const lo = Math.min(selection.start, selection.end);
  const hi = Math.max(selection.start, selection.end);
  return line >= lo && line <= hi;
}

const EXPAND_STEP = 20;
const AUTO_EXPAND_MAX = 400;

function lineClass(kind: RenderedKind): string {
  if (kind === "add") return "bg-diff-add/40";
  if (kind === "del") return "bg-diff-del/40";
  // Lines fetched via Expand up/down sit outside the PR's diff and aren't
  // commentable via GitHub's public API. A very subtle gray differentiates
  // them from the real hunk lines so the user knows what's anchorable.
  if (kind === "ctx-fetched") return "bg-muted/30";
  return "";
}

function prefixClass(kind: RenderedKind): string {
  if (kind === "add") return "text-emerald-700 dark:text-emerald-400";
  if (kind === "del") return "text-rose-700 dark:text-rose-400";
  return "text-muted-foreground";
}

type RenderedKind = LineKind | "ctx-fetched";

interface RenderedRow {
  /** Stable key for React reconciliation. */
  key: string;
  kind: RenderedKind;
  prefix: string;
  oldLine: number | null;
  newLine: number | null;
  tokens: ThemedToken[];
}

function fallbackLines(content: string): DiffLine[] {
  return classifyDiff(content).map((c) => ({
    kind: c.kind,
    raw: c.raw,
    prefix: c.prefix,
    tokens: [{ content: c.body, offset: 0 }],
  }));
}

function computeLineNumbers(
  lines: DiffLine[],
  hunk: Hunk,
): { oldLines: (number | null)[]; newLines: (number | null)[] } {
  const oldLines: (number | null)[] = new Array(lines.length).fill(null);
  const newLines: (number | null)[] = new Array(lines.length).fill(null);
  let oldCursor = hunk.old_start;
  let newCursor = hunk.new_start;
  for (let i = 0; i < lines.length; i++) {
    const k = lines[i].kind;
    if (k === "hunk") continue;
    if (k === "add") {
      newLines[i] = newCursor++;
    } else if (k === "del") {
      oldLines[i] = oldCursor++;
    } else {
      oldLines[i] = oldCursor++;
      newLines[i] = newCursor++;
    }
  }
  return { oldLines, newLines };
}

function distanceToHunk(h: Hunk, line: number): number {
  const start = h.new_start;
  const end = h.new_start + Math.max(h.new_count, 1) - 1;
  if (line < start) return start - line;
  if (line > end) return line - end;
  return 0;
}

/** Decide if THIS hunk should host a comment anchored at ``line``.
 * The rule: closest hunk to the line; ties broken by smallest ``new_start``. */
function ownsLine(
  hunk: Hunk,
  siblings: Hunk[],
  line: number,
): boolean {
  if (siblings.length <= 1) return true;
  const myDist = distanceToHunk(hunk, line);
  const minDist = siblings.reduce(
    (m, s) => Math.min(m, distanceToHunk(s, line)),
    Number.POSITIVE_INFINITY,
  );
  if (myDist !== minDist) return false;
  const tied = siblings.filter((s) => distanceToHunk(s, line) === minDist);
  if (tied.length === 1) return true;
  tied.sort((a, b) => a.new_start - b.new_start || a.id.localeCompare(b.id));
  return tied[0].id === hunk.id;
}

interface HunkViewProps {
  hunk: Hunk;
  /** All hunks for ``hunk.file_path`` within the current thread. Used to decide
   * which hunk hosts each anchored comment, so a single comment doesn't render
   * inside every hunk for the file. */
  siblingsForFile?: Hunk[];
  walkthroughUuid?: string;
  collapseSignal?: number;
  expandSignal?: number;
  stickyTop?: string;
}

export function HunkView({
  hunk,
  siblingsForFile,
  walkthroughUuid,
  collapseSignal = 0,
  expandSignal = 0,
  stickyTop,
}: HunkViewProps) {
  const siblings = siblingsForFile ?? [hunk];
  const fallback = useMemo(() => fallbackLines(hunk.content), [hunk.content]);
  const [hunkLines, setHunkLines] = useState<DiffLine[]>(fallback);
  const [collapsed, setCollapsed] = useState(false);
  const [above, setAbove] = useState<RenderedRow[]>([]);
  const [below, setBelow] = useState<RenderedRow[]>([]);
  const [aboveBusy, setAboveBusy] = useState(false);
  const [belowBusy, setBelowBusy] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  // Tracks the lowest fetched line above the hunk (1-based). Default = hunk.new_start.
  const aboveStart = above.length > 0 ? above[0].newLine ?? hunk.new_start : hunk.new_start;
  const belowEnd =
    below.length > 0
      ? below[below.length - 1].newLine ?? hunk.new_start + hunk.new_count - 1
      : hunk.new_start + hunk.new_count - 1;

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
      setHunkLines(fallback);
      return;
    }
    let cancelled = false;
    highlightDiff(hunk.content, hunk.file_path).then((highlighted) => {
      if (!cancelled) setHunkLines(highlighted);
    });
    return () => {
      cancelled = true;
    };
  }, [hunk.content, hunk.file_path, fallback]);

  // Comments for this PR — shared cache across every HunkView.
  const commentsQuery = useQuery({
    queryKey: ["comments", walkthroughUuid],
    queryFn: () => api.listComments(walkthroughUuid!),
    enabled: !!walkthroughUuid,
    refetchInterval: 30_000,
    retry: (failureCount, err) =>
      err instanceof ApiError && err.status === 404 ? false : failureCount < 1,
  });

  // Threads anchored to THIS file that this hunk owns (closest to the anchor).
  const ownedThreads = useMemo<CommentThread[]>(() => {
    const all = commentsQuery.data?.comments ?? [];
    const forFile = all.filter(
      (c) =>
        c.kind === "review_comment" &&
        c.anchor?.path === hunk.file_path &&
        c.anchor.line != null,
    );
    const allThreads = groupReviewCommentThreads(forFile);
    return allThreads.filter((t) => {
      const line = t.root.anchor?.line;
      if (line == null) return false;
      return ownsLine(hunk, siblings, line);
    });
  }, [commentsQuery.data, hunk, siblings]);

  // Auto-expand for owned threads whose anchor falls outside the visible
  // window. Only handles RIGHT-side anchors (we'd need the base SHA to fetch
  // LEFT-file content); LEFT anchors out of range fall into the outdated list.
  useEffect(() => {
    if (!walkthroughUuid || ownedThreads.length === 0) return;
    let aboveTarget = hunk.new_start;
    let belowTarget = hunk.new_start + hunk.new_count - 1;
    for (const t of ownedThreads) {
      const a = t.root.anchor;
      if (!a || a.line == null || t.root.is_outdated) continue;
      if ((a.side ?? "RIGHT") !== "RIGHT") continue;
      if (a.line < aboveTarget) aboveTarget = a.line;
      if (a.line > belowTarget) belowTarget = a.line;
    }
    if (aboveTarget < aboveStart) {
      const lo = Math.max(1, aboveTarget);
      const lines = aboveStart - lo;
      if (lines > 0 && lines <= AUTO_EXPAND_MAX) {
        void loadAbove(lo, aboveStart - 1);
      }
    }
    if (belowTarget > belowEnd) {
      const hi = belowTarget;
      const lines = hi - belowEnd;
      if (lines > 0 && lines <= AUTO_EXPAND_MAX) {
        void loadBelow(belowEnd + 1, hi);
      }
    }
    // We intentionally exclude loadAbove/loadBelow from the dep list — they
    // capture mutable state via closures and re-running them on each render
    // would loop. ownedThreads + the boundary cursors are the trigger.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ownedThreads, aboveStart, belowEnd, walkthroughUuid]);

  async function fetchSlice(lo: number, hi: number): Promise<RenderedRow[]> {
    if (!walkthroughUuid) return [];
    const slice = await api.fetchPrFile(
      walkthroughUuid,
      hunk.file_path,
      lo,
      hi,
    );
    return highlightFileSlice(slice.lines, hunk.file_path);
  }

  async function loadAbove(lo: number, hi: number) {
    if (aboveBusy) return;
    setAboveBusy(true);
    setFetchError(null);
    try {
      const rows = await fetchSlice(lo, hi);
      setAbove((prev) => mergeUniqueSorted([...rows, ...prev], "asc"));
    } catch (err) {
      setFetchError((err as Error).message);
    } finally {
      setAboveBusy(false);
    }
  }

  async function loadBelow(lo: number, hi: number) {
    if (belowBusy) return;
    setBelowBusy(true);
    setFetchError(null);
    try {
      const rows = await fetchSlice(lo, hi);
      setBelow((prev) => mergeUniqueSorted([...prev, ...rows], "asc"));
    } catch (err) {
      setFetchError((err as Error).message);
    } finally {
      setBelowBusy(false);
    }
  }

  const headerStyle: CSSProperties | undefined = stickyTop
    ? { position: "sticky", top: stickyTop, zIndex: 10 }
    : undefined;

  const { oldLines, newLines } = useMemo(
    () => computeLineNumbers(hunkLines, hunk),
    [hunkLines, hunk],
  );

  const rows: RenderedRow[] = useMemo(() => {
    const hunkRows: RenderedRow[] = hunkLines
      .map<RenderedRow | null>((line, i) => {
        if (line.kind === "hunk") return null; // we render our own header
        return {
          key: `h:${hunk.id}:${i}`,
          kind: line.kind,
          prefix: line.prefix || " ",
          oldLine: oldLines[i],
          newLine: newLines[i],
          tokens: line.tokens,
        };
      })
      .filter((x): x is RenderedRow => x !== null);
    return [...above, ...hunkRows, ...below];
  }, [hunkLines, oldLines, newLines, above, below, hunk.id]);

  // Group threads by the newLine they should anchor to. We render after that
  // row. For LEFT-side anchors, hang the thread off the oldLine row instead.
  const threadsByRowKey = useMemo<Map<string, CommentThread[]>>(() => {
    const map = new Map<string, CommentThread[]>();
    if (ownedThreads.length === 0) return map;
    // Index rows for fast lookup.
    const byNew = new Map<number, RenderedRow>();
    const byOld = new Map<number, RenderedRow>();
    for (const r of rows) {
      if (r.newLine != null) byNew.set(r.newLine, r);
      if (r.oldLine != null && r.kind === "del") byOld.set(r.oldLine, r);
    }
    for (const t of ownedThreads) {
      const a = t.root.anchor;
      if (!a || a.line == null || t.root.is_outdated) continue;
      const useOld = a.side === "LEFT";
      const row = useOld ? byOld.get(a.line) : byNew.get(a.line);
      if (!row) continue;
      const bucket = map.get(row.key) ?? [];
      bucket.push(t);
      map.set(row.key, bucket);
    }
    return map;
  }, [ownedThreads, rows]);

  const orphanThreads = useMemo<CommentThread[]>(() => {
    if (ownedThreads.length === 0) return [];
    const placed = new Set<string>();
    for (const ts of threadsByRowKey.values()) {
      for (const t of ts) placed.add(t.root.id);
    }
    return ownedThreads.filter(
      (t) => t.root.is_outdated || !placed.has(t.root.id),
    );
  }, [ownedThreads, threadsByRowKey]);

  // ---- Inline review-comment selection ---------------------------------
  // ``selection`` is the live drag; ``draftAnchor`` is what the inline
  // composer renders against. On mousedown we set selection; on mousemove
  // we extend it; on mouseup we promote it to a draft (commit).
  const [selection, setSelection] = useState<LineSelection | null>(null);
  const [draftAnchor, setDraftAnchor] = useState<LineSelection | null>(null);

  useEffect(() => {
    if (!selection) return;
    const onUp = () => {
      setDraftAnchor((prev) => {
        // If a draft is already open and the user re-clicks the same line
        // (no drag), keep the existing draft so we don't blow away their
        // unsaved text. Otherwise promote the live selection.
        if (
          prev &&
          prev.side === selection.side &&
          prev.start === selection.start &&
          prev.end === selection.end
        ) {
          return prev;
        }
        return { ...selection };
      });
      setSelection(null);
    };
    document.addEventListener("mouseup", onUp);
    return () => document.removeEventListener("mouseup", onUp);
  }, [selection]);

  function startSelection(row: RenderedRow) {
    const side = selectableSide(row);
    if (!side) return;
    const line = lineForSide(row, side);
    if (line == null) return;
    setSelection({ side, start: line, end: line });
  }

  function extendSelection(row: RenderedRow) {
    setSelection((sel) => {
      if (!sel) return sel;
      const lineOnSide = lineForSide(row, sel.side);
      if (lineOnSide == null) return sel; // not selectable on this side
      if (lineOnSide === sel.end) return sel;
      return { ...sel, end: lineOnSide };
    });
  }

  function isDraftAnchorRow(row: RenderedRow): boolean {
    if (!draftAnchor) return false;
    const line = lineForSide(row, draftAnchor.side);
    if (line == null) return false;
    return line === Math.max(draftAnchor.start, draftAnchor.end);
  }

  return (
    <article
      id={`hunk-${hunk.id}`}
      data-hunk-id={hunk.id}
      data-file-path={hunk.file_path}
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
          aria-label={collapsed ? "Expand file" : "Collapse file"}
          aria-expanded={!collapsed}
          title={collapsed ? "Expand file" : "Collapse file"}
          className="inline-flex size-6 shrink-0 items-center justify-center rounded-md border border-transparent text-muted-foreground hover:border-border hover:bg-background hover:text-foreground"
        >
          {collapsed ? (
            <ChevronRight className="size-4" aria-hidden="true" />
          ) : (
            <ChevronDown className="size-4" aria-hidden="true" />
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
          <pre className="shiki-diff m-0 font-mono text-xs leading-5">
            <ExpandRow
              direction="up"
              available={aboveStart > 1}
              busy={aboveBusy}
              onClick={() => {
                const hi = aboveStart - 1;
                const lo = Math.max(1, hi - EXPAND_STEP + 1);
                if (hi >= lo) void loadAbove(lo, hi);
              }}
            />
            {rows.map((row) => (
              <CodeAndThreads
                key={row.key}
                row={row}
                hunkId={hunk.id}
                filePath={hunk.file_path}
                threads={threadsByRowKey.get(row.key) ?? []}
                walkthroughUuid={walkthroughUuid}
                isSelected={
                  isLineInSelection(row, selection) ||
                  isLineInSelection(row, draftAnchor)
                }
                draftAnchor={isDraftAnchorRow(row) ? draftAnchor : null}
                isSelecting={!!selection}
                onStartSelection={() => startSelection(row)}
                onExtendSelection={() => extendSelection(row)}
                onCancelDraft={() => setDraftAnchor(null)}
              />
            ))}
            <ExpandRow
              direction="down"
              available={true}
              busy={belowBusy}
              onClick={() => {
                const lo = belowEnd + 1;
                const hi = lo + EXPAND_STEP - 1;
                void loadBelow(lo, hi);
              }}
            />
            {fetchError && (
              <div className="px-3 py-1.5 text-[11px] text-destructive">
                Failed to expand context: {fetchError}
              </div>
            )}
            {orphanThreads.length > 0 && (
              <OutdatedThreads
                threads={orphanThreads}
                walkthroughUuid={walkthroughUuid}
              />
            )}
          </pre>
        </div>
      )}
    </article>
  );
}

function ExpandRow({
  direction,
  available,
  busy,
  onClick,
}: {
  direction: "up" | "down";
  available: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  if (!available && !busy) return null;
  const Icon = direction === "up" ? ChevronsUp : ChevronsDown;
  return (
    <div className="flex items-stretch border-y bg-muted/40">
      <button
        type="button"
        onClick={onClick}
        disabled={busy}
        className="flex items-center gap-1.5 px-2 py-1 text-[11px] text-muted-foreground hover:bg-accent hover:text-foreground disabled:cursor-not-allowed disabled:opacity-60"
      >
        {busy ? (
          <Loader2 className="size-3 animate-spin" />
        ) : (
          <Icon className="size-3" />
        )}
        Expand {direction === "up" ? "up" : "down"}
      </button>
      <span className="flex-1 select-none px-2 py-1 text-[10px] text-muted-foreground">
        Click to load {EXPAND_STEP} more lines{" "}
        {direction === "up" ? "above" : "below"}.
      </span>
    </div>
  );
}

function CodeAndThreads({
  row,
  hunkId,
  filePath,
  threads,
  walkthroughUuid,
  isSelected,
  draftAnchor,
  isSelecting,
  onStartSelection,
  onExtendSelection,
  onCancelDraft,
}: {
  row: RenderedRow;
  hunkId: string;
  filePath: string;
  threads: CommentThread[];
  walkthroughUuid?: string;
  isSelected: boolean;
  draftAnchor: LineSelection | null;
  isSelecting: boolean;
  onStartSelection: () => void;
  onExtendSelection: () => void;
  onCancelDraft: () => void;
}) {
  return (
    <>
      <CodeLineRow
        row={row}
        hunkId={hunkId}
        isSelected={isSelected}
        isSelecting={isSelecting}
        onStartSelection={onStartSelection}
        onExtendSelection={onExtendSelection}
      />
      {threads.map((t) => (
        <InlineThreadRow
          key={t.root.id}
          thread={t}
          walkthroughUuid={walkthroughUuid}
        />
      ))}
      {draftAnchor && walkthroughUuid && (
        <NewCommentDraftRow
          walkthroughUuid={walkthroughUuid}
          filePath={filePath}
          anchor={draftAnchor}
          onClose={onCancelDraft}
        />
      )}
    </>
  );
}

function CodeLineRow({
  row,
  hunkId,
  isSelected,
  isSelecting,
  onStartSelection,
  onExtendSelection,
}: {
  row: RenderedRow;
  hunkId: string;
  isSelected: boolean;
  isSelecting: boolean;
  onStartSelection: () => void;
  onExtendSelection: () => void;
}) {
  const side = selectableSide(row);
  return (
    <div
      data-hunk-id={hunkId}
      data-line-old={row.oldLine ?? undefined}
      data-line-new={row.newLine ?? undefined}
      onMouseEnter={isSelecting ? onExtendSelection : undefined}
      className={cn(
        "group relative flex whitespace-pre",
        lineClass(row.kind),
        row.kind === "ctx-fetched" && "opacity-80",
        // GitHub-style yellow wash on selected lines (the soft #fff8c5 vibe).
        // We use important so the diff add/del background doesn't override it
        // when the user drags a selection over a hunk line.
        isSelected && "!bg-yellow-100 dark:!bg-yellow-500/20",
      )}
    >
      {side && (
        <button
          type="button"
          onMouseDown={(e) => {
            e.preventDefault();
            onStartSelection();
          }}
          aria-label="Add a comment on this line"
          title="Add a comment (drag to select multiple lines)"
          className={cn(
            "absolute left-[5.5rem] top-1/2 z-10 -translate-x-1/2 -translate-y-1/2",
            "flex size-4 items-center justify-center rounded-sm",
            "bg-blue-600 text-white shadow-sm hover:bg-blue-700",
            "opacity-0 group-hover:opacity-100",
            isSelected && "opacity-100",
            "transition-opacity",
          )}
        >
          <Plus className="size-3" aria-hidden="true" />
        </button>
      )}
      <Gutter line={row.oldLine} kind={row.kind} side="old" />
      <Gutter line={row.newLine} kind={row.kind} side="new" />
      <span
        className={cn(
          "w-5 shrink-0 select-none text-center",
          prefixClass(row.kind),
        )}
        aria-hidden="true"
      >
        {row.kind === "add" ? "+" : row.kind === "del" ? "−" : row.prefix || " "}
      </span>
      <span className="flex-1 pr-3">
        {row.tokens.length === 0
          ? " "
          : row.tokens.map((token, j) => (
              <span
                key={j}
                style={token.htmlStyle as CSSProperties | undefined}
              >
                {token.content}
              </span>
            ))}
      </span>
    </div>
  );
}

function NewCommentDraftRow({
  walkthroughUuid,
  filePath,
  anchor,
  onClose,
}: {
  walkthroughUuid: string;
  filePath: string;
  anchor: LineSelection;
  onClose: () => void;
}) {
  const queryClient = useQueryClient();
  const [body, setBody] = useState("");
  const addToReview = usePendingReviewStore((s) => s.addComment);
  const hasPendingReview = usePendingReviewStore(
    (s) => (s.drafts[walkthroughUuid]?.comments.length ?? 0) > 0,
  );

  const lo = Math.min(anchor.start, anchor.end);
  const hi = Math.max(anchor.start, anchor.end);
  const isMultiLine = hi > lo;
  const rangeLabel = isMultiLine
    ? `${anchor.side === "LEFT" ? "L" : "R"}${lo}–${anchor.side === "LEFT" ? "L" : "R"}${hi}`
    : `${anchor.side === "LEFT" ? "L" : "R"}${hi}`;

  const submitSingle = useMutation({
    mutationFn: () =>
      api.createReviewComment(walkthroughUuid, {
        body,
        path: filePath,
        line: hi,
        side: anchor.side,
        start_line: isMultiLine ? lo : null,
        start_side: isMultiLine ? anchor.side : null,
      }),
    onSuccess: () => {
      setBody("");
      queryClient.invalidateQueries({
        queryKey: ["comments", walkthroughUuid],
      });
      onClose();
    },
  });

  const stageForReview = () => {
    if (!body.trim()) return;
    addToReview(walkthroughUuid, {
      id: newPendingId(),
      path: filePath,
      line: hi,
      side: anchor.side,
      start_line: isMultiLine ? lo : null,
      start_side: isMultiLine ? anchor.side : null,
      body: body.trim(),
      stagedAt: new Date().toISOString(),
    });
    setBody("");
    onClose();
  };

  const handleSubmit = () => {
    if (!body.trim() || submitSingle.isPending) return;
    submitSingle.mutate();
  };

  return (
    <div className="border-y bg-muted/30 px-3 py-2 font-sans text-sm">
      <header className="mb-2 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span className="font-mono">
          New {isMultiLine ? "multi-line " : ""}comment on lines {rangeLabel}
        </span>
        <button
          type="button"
          onClick={onClose}
          className="hover:text-foreground"
        >
          Dismiss
        </button>
      </header>
      <CommentComposer
        value={body}
        onChange={setBody}
        onSubmit={handleSubmit}
        onCancel={onClose}
        autoFocus
        placeholder="Leave a comment (Markdown supported)…"
        actions={
          <>
            <button
              type="button"
              onClick={onClose}
              className="text-[11px] text-muted-foreground hover:text-foreground"
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={stageForReview}
              disabled={!body.trim() || submitSingle.isPending}
              className="inline-flex items-center gap-1 rounded border border-blue-300 bg-blue-50 px-2 py-0.5 text-[11px] font-medium text-blue-800 hover:bg-blue-100 disabled:cursor-not-allowed disabled:opacity-50 dark:border-blue-700/60 dark:bg-blue-950/60 dark:text-blue-200 dark:hover:bg-blue-900/60"
            >
              {hasPendingReview ? "Add to review" : "Start a review"}
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              disabled={!body.trim() || submitSingle.isPending}
              className="inline-flex items-center gap-1 rounded-md bg-foreground px-2 py-0.5 text-[11px] font-medium text-background disabled:cursor-not-allowed disabled:opacity-50"
            >
              {submitSingle.isPending ? (
                <Loader2 className="size-3 animate-spin" />
              ) : null}
              {submitSingle.isPending ? "Posting…" : "Add single comment"}
            </button>
          </>
        }
      />
      {submitSingle.error && (
        <p className="mt-1.5 text-[11px] text-destructive">
          {(submitSingle.error as Error).message}
        </p>
      )}
    </div>
  );
}

function Gutter({
  line,
  kind,
  side,
}: {
  line: number | null;
  kind: RenderedKind;
  side: "old" | "new";
}) {
  const bgClass =
    kind === "add"
      ? side === "old"
        ? "bg-diff-add/20"
        : "bg-diff-add/30"
      : kind === "del"
        ? side === "old"
          ? "bg-diff-del/30"
          : "bg-diff-del/20"
        : "bg-muted/40";
  return (
    <span
      className={cn(
        "w-12 shrink-0 select-none border-r px-2 text-right text-[10px] leading-5 text-muted-foreground",
        bgClass,
      )}
      aria-label={`${side}-file line ${line ?? ""}`}
    >
      {line ?? ""}
    </span>
  );
}

function InlineThreadRow({
  thread,
  walkthroughUuid,
}: {
  thread: CommentThread;
  walkthroughUuid?: string;
}) {
  const anchor = thread.root.anchor;
  const title = anchor ? threadTitle(anchor) : "Comment";
  return (
    <div className="border-y bg-muted/30 px-3 py-2 font-sans text-sm">
      <header className="mb-2 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
        <span className="font-mono">{title}</span>
        {thread.root.html_url && (
          <a
            href={thread.root.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 hover:text-foreground"
          >
            Open on GitHub
            <ExternalLink className="size-2.5" />
          </a>
        )}
      </header>
      <ThreadComment comment={thread.root} />
      {thread.replies.length > 0 && (
        <ul className="mt-2 space-y-2 border-l-2 border-muted pl-3">
          {thread.replies.map((r) => (
            <li key={r.id}>
              <ThreadComment comment={r} compact />
            </li>
          ))}
        </ul>
      )}
      {walkthroughUuid && (
        <div className="mt-2">
          <ReplyComposer
            walkthroughUuid={walkthroughUuid}
            parentCommentId={thread.root.id}
          />
        </div>
      )}
    </div>
  );
}

function OutdatedThreads({
  threads,
  walkthroughUuid,
}: {
  threads: CommentThread[];
  walkthroughUuid?: string;
}) {
  return (
    <div className="border-t bg-muted/30 px-3 py-2 font-sans text-xs">
      <p className="mb-2 inline-flex items-center gap-1.5 rounded bg-muted px-2 py-0.5 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
        Comments marked as outdated
      </p>
      <ul className="space-y-2">
        {threads.map((t) => (
          <li
            key={t.root.id}
            className="rounded-md border border-dashed bg-background/60 px-2.5 py-2"
          >
            <header className="mb-1 flex items-center justify-between gap-2 text-[11px] text-muted-foreground">
              <span className="font-mono">
                {t.root.anchor ? threadTitle(t.root.anchor) : "Comment"}
              </span>
              {t.root.html_url && (
                <a
                  href={t.root.html_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-flex items-center gap-1 hover:text-foreground"
                >
                  GitHub
                  <ExternalLink className="size-2.5" />
                </a>
              )}
            </header>
            <ThreadComment comment={t.root} compact />
            {t.replies.length > 0 && (
              <ul className="mt-1.5 space-y-1.5 border-l-2 border-muted pl-2.5">
                {t.replies.map((r) => (
                  <li key={r.id}>
                    <ThreadComment comment={r} compact />
                  </li>
                ))}
              </ul>
            )}
            {walkthroughUuid && (
              <div className="mt-1.5">
                <ReplyComposer
                  walkthroughUuid={walkthroughUuid}
                  parentCommentId={t.root.id}
                />
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function ThreadComment({
  comment,
  compact = false,
}: {
  comment: CommentDTO;
  compact?: boolean;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5">
        {comment.author_avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={comment.author_avatar_url}
            alt=""
            className={compact ? "size-3.5 rounded-full" : "size-4 rounded-full"}
          />
        ) : null}
        <span className={compact ? "text-[11px] font-medium" : "text-xs font-medium"}>
          {comment.author_login ?? "unknown"}
        </span>
        <SyncBadge comment={comment} />
        {comment.created_at && (
          <time className="ml-1 text-[10px] text-muted-foreground">
            {formatDate(comment.created_at)}
          </time>
        )}
      </div>
      <Markdown className={compact ? "mt-1 text-[11px]" : "mt-1 text-xs"}>
        {comment.body || "_(empty)_"}
      </Markdown>
    </div>
  );
}

function SyncBadge({ comment }: { comment: CommentDTO }) {
  if (comment.sync_state === "syncing" || comment.sync_state === "local") {
    return (
      <span className="rounded-full bg-amber-100 px-1 py-px text-[8px] uppercase tracking-wider text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
        syncing
      </span>
    );
  }
  if (comment.sync_state === "failed") {
    return (
      <span
        className="rounded-full bg-rose-100 px-1 py-px text-[8px] uppercase tracking-wider text-rose-700 dark:bg-rose-500/10 dark:text-rose-300"
        title={comment.sync_error ?? undefined}
      >
        failed
      </span>
    );
  }
  return null;
}

function ReplyComposer({
  walkthroughUuid,
  parentCommentId,
}: {
  walkthroughUuid: string;
  parentCommentId: string;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);
  const submit = useMutation({
    mutationFn: (body: string) =>
      api.replyToComment(walkthroughUuid, parentCommentId, body),
    onSuccess: () => {
      setDraft("");
      setOpen(false);
      queryClient.invalidateQueries({
        queryKey: ["comments", walkthroughUuid],
      });
    },
  });
  if (!open) {
    return (
      <button
        type="button"
        onClick={() => setOpen(true)}
        className="text-[11px] text-muted-foreground hover:text-foreground"
      >
        Reply
      </button>
    );
  }
  const handleSubmit = () => {
    const v = draft.trim();
    if (!v || submit.isPending) return;
    submit.mutate(v);
  };
  const handleCancel = () => {
    setOpen(false);
    setDraft("");
  };
  return (
    <CommentComposer
      value={draft}
      onChange={setDraft}
      onSubmit={handleSubmit}
      onCancel={handleCancel}
      compact
      rows={2}
      autoFocus
      placeholder="Reply (Markdown supported)…"
      actions={
        <>
          <button
            type="button"
            onClick={handleCancel}
            className="text-[10px] text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSubmit}
            disabled={!draft.trim() || submit.isPending}
            className="inline-flex items-center gap-1 rounded-md bg-foreground px-2 py-0.5 text-[11px] font-medium text-background disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submit.isPending ? <Loader2 className="size-3 animate-spin" /> : null}
            {submit.isPending ? "Sending…" : "Reply"}
          </button>
        </>
      }
    />
  );
}

function threadTitle(anchor: NonNullable<CommentDTO["anchor"]>): string {
  const side = (anchor.side ?? "RIGHT") === "LEFT" ? "L" : "R";
  if (
    anchor.start_line != null &&
    anchor.line != null &&
    anchor.start_line !== anchor.line
  ) {
    const startSide =
      (anchor.start_side ?? anchor.side ?? "RIGHT") === "LEFT" ? "L" : "R";
    return `Comment on lines ${startSide}${anchor.start_line} to ${side}${anchor.line}`;
  }
  return `Comment on line ${side}${anchor.line}`;
}

function mergeUniqueSorted(rows: RenderedRow[], _dir: "asc"): RenderedRow[] {
  // Dedupe by newLine (we only fetch by new-file line numbers).
  const seen = new Map<number, RenderedRow>();
  for (const r of rows) {
    if (r.newLine == null) continue;
    seen.set(r.newLine, r);
  }
  return [...seen.values()].sort((a, b) => (a.newLine ?? 0) - (b.newLine ?? 0));
}

async function highlightFileSlice(
  lines: { line: number; content: string }[],
  filePath: string,
): Promise<RenderedRow[]> {
  if (lines.length === 0) return [];
  const lang = languageForPath(filePath);
  const code = lines.map((l) => l.content).join("\n");
  if (lang === "text") {
    return lines.map((l) => ({
      key: `f:${filePath}:${l.line}`,
      kind: "ctx-fetched" as const,
      prefix: " ",
      oldLine: null,
      newLine: l.line,
      tokens: [{ content: l.content, offset: 0 }],
    }));
  }
  try {
    const highlighter = await getDiffHighlighter();
    if (!highlighter.getLoadedLanguages().includes(lang)) {
      await highlighter.loadLanguage(lang);
    }
    const result = highlighter.codeToTokens(code, {
      lang,
      themes: { light: LIGHT_THEME, dark: DARK_THEME },
      defaultColor: false,
    });
    return lines.map((l, i) => ({
      key: `f:${filePath}:${l.line}`,
      kind: "ctx-fetched" as const,
      prefix: " ",
      oldLine: null,
      newLine: l.line,
      tokens: result.tokens[i] ?? [{ content: l.content, offset: 0 }],
    }));
  } catch {
    return lines.map((l) => ({
      key: `f:${filePath}:${l.line}`,
      kind: "ctx-fetched" as const,
      prefix: " ",
      oldLine: null,
      newLine: l.line,
      tokens: [{ content: l.content, offset: 0 }],
    }));
  }
}

// Backwards compat: layout still imports this event name even though no one
// listens anymore. Keeping it avoids a needless cross-file edit just to
// remove an unused export.
export const HUNK_COLLAPSE_EVENT = "unravel:hunk-collapse-change";
