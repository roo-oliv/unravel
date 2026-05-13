"use client";

import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";

import type { FieldEditDTO } from "@/lib/api";
import { useUiSettings } from "@/lib/ui-settings";
import { cn } from "@/lib/utils";

import { EditableField } from "./editable-field";
import { HunkView } from "./hunk-view";
import { Markdown } from "./markdown";
import { OverviewPrSection } from "./overview-pr-section";
import {
  hunkRefs,
  type Hunk,
  type Thread,
  type ThreadStepDTO,
  type Walkthrough,
} from "./types";

// Hysteresis thresholds for switching the thread header between big/compact.
// Browser scroll-anchoring + a single threshold caused flicker: the layout
// shift when the big header collapses re-crosses the threshold, snapping back.
// Two thresholds (and overflow-anchor: none) keep the state stable across the
// layout shift.
const SHRINK_AT = 100;
const EXPAND_AT = 30;

interface Props {
  walkthrough: Walkthrough;
  thread: Thread | null; // null = overview
  hunkIndex: Record<string, Hunk>;
  collapseSignal?: number;
  expandSignal?: number;
  slug?: string;
  walkthroughUuid?: string;
  historyByKey: Record<string, FieldEditDTO[]>;
}

const EMPTY_HISTORY: FieldEditDTO[] = [];

function lookupHistory(
  historyByKey: Record<string, FieldEditDTO[]>,
  targetKind: "walkthrough" | "thread" | "step",
  targetUuid: string | undefined,
  field: string,
): FieldEditDTO[] {
  if (!targetUuid) return EMPTY_HISTORY;
  return historyByKey[`${targetKind}:${targetUuid}:${field}`] ?? EMPTY_HISTORY;
}

export function ThreadStage({
  walkthrough,
  thread,
  hunkIndex,
  collapseSignal = 0,
  expandSignal = 0,
  slug,
  walkthroughUuid,
  historyByKey,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const threadHeaderRef = useRef<HTMLElement>(null);
  const [scrolled, setScrolled] = useState(false);
  const fullWidth = useUiSettings((s) => s.fullWidth);
  const overviewWidth = fullWidth ? "w-full" : "mx-auto max-w-3xl";
  const threadWidth = fullWidth ? "w-full" : "mx-auto max-w-4xl";

  // For each file path touched by this thread, list every hunk that touches
  // it (preserving order). HunkView uses this to figure out which hunk should
  // host each anchored comment.
  const hunksByFileInThread = useMemo<Record<string, Hunk[]>>(() => {
    const map: Record<string, Hunk[]> = {};
    if (!thread) return map;
    for (const step of thread.steps) {
      for (const ref of hunkRefs(step)) {
        const h = hunkIndex[ref];
        if (!h?.file_path) continue;
        (map[h.file_path] ??= []).push(h);
      }
    }
    return map;
  }, [thread, hunkIndex]);

  // Reset scroll + attach scroll listener whenever thread changes (the scroll
  // container element is recreated for overview vs thread views).
  useEffect(() => {
    const el = scrollRef.current;
    if (!el) return;
    el.scrollTop = 0;
    setScrolled(false);
    // Local mirror so the listener doesn't capture stale React state.
    let isScrolled = false;
    const onScroll = () => {
      const top = el.scrollTop;
      if (!isScrolled && top > SHRINK_AT) {
        isScrolled = true;
        setScrolled(true);
      } else if (isScrolled && top < EXPAND_AT) {
        isScrolled = false;
        setScrolled(false);
      }
    };
    el.addEventListener("scroll", onScroll, { passive: true });
    return () => el.removeEventListener("scroll", onScroll);
  }, [thread?.id]);

  // Publish thread-header height as a CSS var on the scroll container so
  // step/hunk sticky headers can stack exactly below it (no gap, no overlap),
  // even while the thread title is mid-morph between big/compact.
  useLayoutEffect(() => {
    const headerEl = threadHeaderRef.current;
    const rootEl = scrollRef.current;
    if (!headerEl || !rootEl) return;
    const measure = () => {
      rootEl.style.setProperty(
        "--thread-h",
        `${headerEl.offsetHeight}px`,
      );
    };
    const ro = new ResizeObserver(measure);
    ro.observe(headerEl);
    measure();
    return () => ro.disconnect();
  }, [thread?.id]);

  if (thread === null) {
    const overviewEditable = !!walkthroughUuid;
    return (
      <div
        ref={scrollRef}
        className="h-full overflow-y-auto bg-background [overflow-anchor:none]"
      >
        <article className={cn(overviewWidth, "px-6 py-8")}>
          <header className="mb-8">
            <h1 className="text-2xl font-semibold tracking-tight">Overview</h1>
          </header>
          {overviewEditable ? (
            <EditableField
              walkthroughUuid={walkthroughUuid!}
              targetKind="walkthrough"
              targetUuid={walkthroughUuid!}
              field="overview"
              originalValue={walkthrough.overview}
              history={lookupHistory(
                historyByKey,
                "walkthrough",
                walkthroughUuid,
                "overview",
              )}
              placeholder="(no overview — click to add)"
              textClassName="text-base text-foreground/90"
            />
          ) : (
            <Markdown className="text-base text-foreground/90">
              {walkthrough.overview}
            </Markdown>
          )}
          <section className="mt-8">
            <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
              Suggested order
            </h2>
            <ol className="space-y-1">
              {walkthrough.suggested_order.map((tid, i) => {
                const t = walkthrough.threads.find((x) => x.id === tid);
                return (
                  <li key={tid} className="flex items-baseline gap-3">
                    <span className="w-6 shrink-0 font-mono text-xs text-muted-foreground">
                      {String(i + 1).padStart(2, "0")}
                    </span>
                    <span className="text-sm">{t?.title ?? tid}</span>
                  </li>
                );
              })}
            </ol>
          </section>
          {walkthroughUuid && walkthrough.pr && (
            <OverviewPrSection walkthroughUuid={walkthroughUuid} />
          )}
        </article>
      </div>
    );
  }

  const threadUuid = thread.uuid;
  const editable = !!walkthroughUuid && !!threadUuid;

  return (
    <div
      ref={scrollRef}
      className="h-full overflow-y-auto bg-background [overflow-anchor:none]"
    >
      {/* Sticky thread title — morphs between big (at top) and compact (scrolled). */}
      <header
        ref={threadHeaderRef}
        className={cn(
          "sticky top-0 z-30 bg-background transition-shadow duration-200",
          scrolled && "shadow-sm",
        )}
      >
        <div className={cn(threadWidth, "px-6")}>
          <div className={scrolled ? "py-2.5" : "pt-8"}>
            {editable ? (
              <EditableField
                walkthroughUuid={walkthroughUuid!}
                targetKind="thread"
                targetUuid={threadUuid!}
                field="title"
                originalValue={thread.title}
                history={lookupHistory(
                  historyByKey,
                  "thread",
                  threadUuid,
                  "title",
                )}
                asMarkdown={false}
                singleLine
                placeholder="Untitled thread"
                textClassName={cn(
                  "truncate",
                  scrolled
                    ? "text-base font-semibold leading-6"
                    : "text-2xl font-semibold leading-tight tracking-tight",
                )}
              />
            ) : (
              <h1
                className={cn(
                  "truncate",
                  scrolled
                    ? "text-base font-semibold leading-6"
                    : "text-2xl font-semibold leading-tight tracking-tight",
                )}
              >
                {thread.title}
              </h1>
            )}
          </div>
          {!scrolled && (
            <div className="pb-8">
              {thread.dependencies.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {thread.dependencies.map((dep) => (
                    <span
                      key={dep}
                      className="inline-flex items-center rounded bg-muted px-2 py-0.5 font-mono text-xs text-muted-foreground"
                    >
                      depends on ↳ {dep}
                    </span>
                  ))}
                </div>
              )}
              {editable ? (
                <div className="mt-4">
                  <EditableField
                    walkthroughUuid={walkthroughUuid!}
                    targetKind="thread"
                    targetUuid={threadUuid!}
                    field="summary"
                    originalValue={thread.summary}
                    history={lookupHistory(
                      historyByKey,
                      "thread",
                      threadUuid,
                      "summary",
                    )}
                    placeholder="(no summary — click to add)"
                    textClassName="text-base text-foreground/90"
                  />
                </div>
              ) : (
                <Markdown className="mt-4 text-base text-foreground/90">
                  {thread.summary}
                </Markdown>
              )}
              <div className="mt-3 text-sm text-muted-foreground">
                <span className="text-[10px] font-medium uppercase tracking-wide">
                  Why
                </span>
                {editable ? (
                  <div className="mt-0.5">
                    <EditableField
                      walkthroughUuid={walkthroughUuid!}
                      targetKind="thread"
                      targetUuid={threadUuid!}
                      field="root_cause"
                      originalValue={thread.root_cause}
                      history={lookupHistory(
                        historyByKey,
                        "thread",
                        threadUuid,
                        "root_cause",
                      )}
                      placeholder="(no root cause — click to add)"
                      textClassName="italic"
                    />
                  </div>
                ) : (
                  thread.root_cause && (
                    <Markdown className="mt-0.5 italic">
                      {thread.root_cause}
                    </Markdown>
                  )
                )}
              </div>
            </div>
          )}
        </div>
        {scrolled && <div className="border-b" aria-hidden="true" />}
      </header>

      <article className={cn(threadWidth, "px-6 pb-16")}>
        <ol>
          {thread.steps.map((step, idx) => (
            <StickyStep
              key={step.id ?? idx}
              step={step}
              idx={idx}
              hunkIndex={hunkIndex}
              hunksByFileInThread={hunksByFileInThread}
              collapseSignal={collapseSignal}
              expandSignal={expandSignal}
              walkthroughUuid={walkthroughUuid}
              historyByKey={historyByKey}
              slug={slug}
            />
          ))}
        </ol>
      </article>
    </div>
  );
}

interface StickyStepProps {
  step: ThreadStepDTO;
  idx: number;
  hunkIndex: Record<string, Hunk>;
  hunksByFileInThread: Record<string, Hunk[]>;
  collapseSignal: number;
  expandSignal: number;
  walkthroughUuid?: string;
  historyByKey: Record<string, FieldEditDTO[]>;
  slug?: string;
}

function StickyStep({
  step,
  idx,
  hunkIndex,
  hunksByFileInThread,
  collapseSignal,
  expandSignal,
  walkthroughUuid,
  historyByKey,
  slug,
}: StickyStepProps) {
  const stepRef = useRef<HTMLLIElement>(null);
  const headerRef = useRef<HTMLDivElement>(null);

  // Mirror the step header's current height to a CSS var on this <li>, so
  // child hunk headers can stack at `var(--thread-h) + var(--step-h)`.
  useLayoutEffect(() => {
    const headerEl = headerRef.current;
    const stepEl = stepRef.current;
    if (!headerEl || !stepEl) return;
    const measure = () => {
      stepEl.style.setProperty("--step-h", `${headerEl.offsetHeight}px`);
    };
    const ro = new ResizeObserver(measure);
    ro.observe(headerEl);
    measure();
    return () => ro.disconnect();
  }, []);

  const editable = !!walkthroughUuid && !!step.id;

  return (
    <li ref={stepRef} className="pt-6">
      <div
        ref={headerRef}
        className="sticky z-20 bg-background pb-3"
        style={{ top: "var(--thread-h, 48px)" }}
      >
        <div className="flex items-baseline gap-3">
          <span className="shrink-0 font-mono text-xs text-muted-foreground">
            Step {step.order || idx + 1}
          </span>
          <div className="min-w-0 flex-1">
            {editable ? (
              <EditableField
                walkthroughUuid={walkthroughUuid!}
                targetKind="step"
                targetUuid={step.id}
                field="narration"
                originalValue={step.narration}
                history={lookupHistory(
                  historyByKey,
                  "step",
                  step.id,
                  "narration",
                )}
                placeholder="(empty — click to add narration)"
                textClassName="text-sm"
              />
            ) : (
              <Markdown className="text-sm">{step.narration}</Markdown>
            )}
          </div>
        </div>
      </div>
      <div className="space-y-3 pl-6">
        {hunkRefs(step).map((ref) => {
          const hunk = hunkIndex[ref];
          if (!hunk) {
            return (
              <div
                key={ref}
                className="rounded border bg-muted/30 px-3 py-2 text-xs italic text-muted-foreground"
              >
                Missing hunk {ref}
              </div>
            );
          }
          return (
            <HunkView
              key={ref}
              hunk={hunk}
              siblingsForFile={hunksByFileInThread[hunk.file_path] ?? [hunk]}
              walkthroughUuid={walkthroughUuid}
              stickyTop="calc(var(--thread-h, 48px) + var(--step-h, 0px))"
              collapseSignal={collapseSignal}
              expandSignal={expandSignal}
              slug={slug}
            />
          );
        })}
      </div>
    </li>
  );
}
