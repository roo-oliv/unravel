"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Check,
  ChevronDown,
  ChevronRight,
  Loader2,
  MessageSquare,
  Settings,
  Undo2,
  X,
} from "lucide-react";
import { useState } from "react";

import { ApiError, api, type PrState, type ReviewEvent } from "@/lib/api";
import { basename } from "@/lib/comment-threads";
import {
  toReviewCommentPayloads,
  usePendingReviewStore,
  type PendingReviewComment,
} from "@/lib/pending-review";
import { cn } from "@/lib/utils";

import { CommentComposer } from "./comment-composer";

interface Props {
  walkthroughUuid: string;
  additions: number;
  deletions: number;
  onOpenSettings?: () => void;
}

function isPrClosedOrMerged(state: PrState | undefined): boolean {
  return state === "merged" || state === "closed";
}

function formatLineCount(n: number): string {
  return n.toLocaleString("en-US");
}

/**
 * Sticky top-of-page bar mirroring GitHub's PR review composer.
 *
 * Always visible while a walkthrough has a PR: shows the +X / −Y line stats
 * and the review submit affordance. When the user stages inline comments the
 * bar lights up blue and the actions become enabled; otherwise it sits in a
 * muted state with disabled actions. An expand chevron reveals the per-comment
 * editor + review summary composer for staged drafts.
 *
 * For open PRs we expose all three GitHub review verbs (Comment / Approve /
 * Request changes). For closed/merged PRs we collapse to a single
 * "Submit comments" button — Approve / Request changes are no-ops post-merge.
 */
export function PendingReviewBar({
  walkthroughUuid,
  additions,
  deletions,
  onOpenSettings,
}: Props) {
  const draft = usePendingReviewStore((s) => s.drafts[walkthroughUuid]);
  const setSummary = usePendingReviewStore((s) => s.setSummary);
  const clear = usePendingReviewStore((s) => s.clear);
  const removeComment = usePendingReviewStore((s) => s.removeComment);
  const updateComment = usePendingReviewStore((s) => s.updateComment);
  const queryClient = useQueryClient();

  const prQuery = useQuery({
    queryKey: ["pr", walkthroughUuid],
    queryFn: () => api.getPr(walkthroughUuid),
    refetchInterval: 60_000,
    retry: (failureCount, err) =>
      err instanceof ApiError && err.status === 404 ? false : failureCount < 1,
  });
  const closedOrMerged = isPrClosedOrMerged(prQuery.data?.state);

  const [expanded, setExpanded] = useState(false);
  const [pendingEvent, setPendingEvent] = useState<ReviewEvent | null>(null);

  const submit = useMutation({
    mutationFn: (event: ReviewEvent) =>
      api.submitReview(walkthroughUuid, {
        event,
        body: draft?.summary || null,
        comments: draft ? toReviewCommentPayloads(draft) : [],
      }),
    onSuccess: () => {
      clear(walkthroughUuid);
      setExpanded(false);
      queryClient.invalidateQueries({
        queryKey: ["comments", walkthroughUuid],
      });
    },
    onSettled: () => setPendingEvent(null),
  });

  const count = draft?.comments.length ?? 0;
  const hasDraft = count > 0;
  const hasStats = additions > 0 || deletions > 0;

  const handleSubmit = (event: ReviewEvent) => {
    if (submit.isPending) return;
    if (event === "REQUEST_CHANGES" && !draft?.summary.trim()) {
      const ok = window.confirm(
        "Request changes without a summary? GitHub requires a body for change requests — they often help reviewers know what to address first.",
      );
      if (!ok) return;
    }
    setPendingEvent(event);
    submit.mutate(event);
  };

  const handleCancel = () => {
    if (submit.isPending) return;
    if (hasDraft) {
      const ok = window.confirm(
        `Discard ${count} pending review comment${count === 1 ? "" : "s"}? This can't be undone.`,
      );
      if (!ok) return;
      clear(walkthroughUuid);
    }
    setExpanded(false);
  };

  return (
    <div
      role="region"
      aria-label="Pending review"
      className={cn(
        "border-b px-4 py-2 text-xs transition-colors",
        hasDraft
          ? "border-blue-200 bg-blue-50 text-blue-900 dark:border-blue-900/60 dark:bg-blue-950/40 dark:text-blue-100"
          : "border-border bg-muted/40 text-muted-foreground",
      )}
    >
      <div className="flex items-center justify-between gap-3">
        <button
          type="button"
          onClick={() => setExpanded((e) => !e)}
          aria-expanded={expanded}
          className="flex min-w-0 flex-1 items-center gap-2 text-left"
        >
          {expanded ? (
            <ChevronDown className="size-3.5 shrink-0" />
          ) : (
            <ChevronRight className="size-3.5 shrink-0" />
          )}
          {hasStats && (
            <span className="flex shrink-0 items-center gap-1.5 font-mono tabular-nums">
              <span className="text-emerald-700 dark:text-emerald-400">
                +{formatLineCount(additions)}
              </span>
              <span className="text-rose-700 dark:text-rose-400">
                −{formatLineCount(deletions)}
              </span>
            </span>
          )}
          {hasDraft ? (
            <>
              {hasStats && <span className="opacity-40">·</span>}
              <MessageSquare className="size-3.5 shrink-0" />
              <span className="font-medium tabular-nums">
                {count} pending review {count === 1 ? "comment" : "comments"}
              </span>
              <span className="hidden text-blue-800/70 sm:inline dark:text-blue-200/70">
                · choose an action to submit
              </span>
            </>
          ) : (
            <>
              {hasStats && <span className="opacity-40">·</span>}
              <MessageSquare className="size-3.5 shrink-0 opacity-70" />
              <span className="hidden sm:inline">No pending review comments</span>
            </>
          )}
        </button>
        <div className="flex shrink-0 items-center gap-2">
          {expanded ? (
            <>
              <DiscardButton
                onClick={handleCancel}
                disabled={submit.isPending}
                tone={hasDraft ? "blue" : "neutral"}
              />
              {!closedOrMerged && (
                <ActionButton
                  label="Approve"
                  icon={<Check className="size-3" />}
                  tone="approve"
                  disabled={submit.isPending}
                  busy={submit.isPending && pendingEvent === "APPROVE"}
                  onClick={() => handleSubmit("APPROVE")}
                />
              )}
              <ActionButton
                label="Comment"
                icon={<MessageSquare className="size-3" />}
                tone="neutral"
                disabled={submit.isPending}
                busy={submit.isPending && pendingEvent === "COMMENT"}
                onClick={() => handleSubmit("COMMENT")}
              />
              {!closedOrMerged && (
                <ActionButton
                  label="Request changes"
                  icon={<AlertCircle className="size-3" />}
                  tone="reject"
                  disabled={submit.isPending}
                  busy={submit.isPending && pendingEvent === "REQUEST_CHANGES"}
                  onClick={() => handleSubmit("REQUEST_CHANGES")}
                />
              )}
            </>
          ) : (
            <SubmitButton
              label={closedOrMerged ? "Submit comments" : "Submit review"}
              disabled={submit.isPending}
              busy={submit.isPending}
              onClick={() => setExpanded(true)}
            />
          )}
          {onOpenSettings && (
            <button
              type="button"
              onClick={onOpenSettings}
              aria-label="Display settings"
              title="Display settings"
              className={cn(
                "inline-flex items-center justify-center rounded border p-1",
                hasDraft
                  ? "border-blue-300 bg-white/60 text-blue-900 hover:bg-white dark:border-blue-800 dark:bg-blue-900/40 dark:text-blue-100 dark:hover:bg-blue-900/60"
                  : "border-border bg-background hover:bg-accent hover:text-foreground",
              )}
            >
              <Settings className="size-3.5" aria-hidden="true" />
            </button>
          )}
        </div>
      </div>
      {submit.error && (
        <SubmitErrorRow message={(submit.error as Error).message} />
      )}
      {expanded && (
        <div className="mt-3 space-y-3">
          <div>
            <label
              className={cn(
                "mb-1 block text-[10px] font-medium uppercase tracking-wider",
                hasDraft
                  ? "text-blue-800/70 dark:text-blue-200/70"
                  : "text-muted-foreground",
              )}
            >
              Review summary (optional)
            </label>
            <CommentComposer
              value={draft?.summary ?? ""}
              onChange={(v) => setSummary(walkthroughUuid, v)}
              rows={3}
              placeholder="Leave an overall comment on this review…"
              compact
            />
          </div>
          {hasDraft && draft && (
            <ul className="space-y-2">
              {draft.comments.map((c) => (
                <li key={c.id}>
                  <DraftCommentRow
                    draft={c}
                    onRemove={() => removeComment(walkthroughUuid, c.id)}
                    onChange={(body) =>
                      updateComment(walkthroughUuid, c.id, { body })
                    }
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

function SubmitErrorRow({ message }: { message: string }) {
  // GitHub's 422 body shows up as raw JSON in the message — try to pull out
  // the human-readable part so the bar stays a single line by default.
  const summary = summariseError(message);
  return (
    <div className="mt-2 flex items-start gap-2 rounded border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[11px] text-rose-900 dark:border-rose-900/60 dark:bg-rose-950/40 dark:text-rose-100">
      <AlertCircle className="mt-0.5 size-3 shrink-0" aria-hidden="true" />
      <div className="min-w-0 flex-1">
        <p className="font-medium">Submit failed: {summary.headline}</p>
        {summary.hint && (
          <p className="mt-0.5 text-rose-800/80 dark:text-rose-200/80">
            {summary.hint}
          </p>
        )}
        <details className="mt-1">
          <summary className="cursor-pointer text-[10px] uppercase tracking-wider text-rose-700/70 hover:text-rose-900 dark:text-rose-300/70 dark:hover:text-rose-100">
            Details
          </summary>
          <pre className="mt-1 max-h-32 overflow-auto whitespace-pre-wrap rounded bg-rose-100/50 px-2 py-1 font-mono text-[10px] dark:bg-rose-900/30">
            {message}
          </pre>
        </details>
      </div>
    </div>
  );
}

function summariseError(message: string): { headline: string; hint?: string } {
  if (message.includes("Line could not be resolved")) {
    return {
      headline: "GitHub couldn't anchor one of the comments.",
      hint:
        "GitHub's review API only accepts comments on lines inside the PR's diff hunks. " +
        "Remove drafts on lines reached via Expand up/down — those lines aren't part of the diff GitHub knows about.",
    };
  }
  if (message.includes("GraphQL errors:")) {
    const tail = message.split("GraphQL errors:").slice(1).join("").trim();
    return {
      headline: tail || "GitHub rejected the review.",
    };
  }
  if (message.includes("Unprocessable Entity")) {
    return {
      headline: "GitHub rejected the review (422).",
      hint: "See details for the raw response.",
    };
  }
  // Truncate raw messages so the bar stays compact.
  if (message.length > 160) {
    return { headline: `${message.slice(0, 160)}…` };
  }
  return { headline: message };
}

function SubmitButton({
  label,
  disabled,
  busy,
  onClick,
}: {
  label: string;
  disabled: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="inline-flex items-center gap-1 rounded bg-emerald-600 px-2 py-1 font-medium text-white hover:bg-emerald-700 disabled:cursor-not-allowed disabled:bg-emerald-600/40 disabled:opacity-70"
    >
      {busy ? (
        <Loader2 className="size-3 animate-spin" aria-hidden="true" />
      ) : (
        <MessageSquare className="size-3" aria-hidden="true" />
      )}
      {label}
    </button>
  );
}

function ActionButton({
  label,
  icon,
  tone,
  disabled,
  busy,
  onClick,
}: {
  label: string;
  icon: React.ReactNode;
  tone: "neutral" | "approve" | "reject";
  disabled: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  const toneClass =
    tone === "approve"
      ? "bg-emerald-600 text-white hover:bg-emerald-700 disabled:bg-emerald-400"
      : tone === "reject"
        ? "bg-rose-600 text-white hover:bg-rose-700 disabled:bg-rose-400"
        : "bg-foreground text-background hover:bg-foreground/90 disabled:bg-foreground/40";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex items-center gap-1 rounded px-2 py-1 font-medium disabled:cursor-not-allowed disabled:opacity-70",
        toneClass,
      )}
    >
      {busy ? (
        <Loader2 className="size-3 animate-spin" aria-hidden="true" />
      ) : (
        icon
      )}
      {label}
    </button>
  );
}

function DiscardButton({
  onClick,
  disabled,
  tone,
}: {
  onClick: () => void;
  disabled: boolean;
  tone: "blue" | "neutral";
}) {
  const className =
    tone === "blue"
      ? "border-blue-300 bg-white/60 text-blue-900 hover:bg-white dark:border-blue-800 dark:bg-blue-900/40 dark:text-blue-100 dark:hover:bg-blue-900/60"
      : "border-border bg-background hover:bg-accent hover:text-foreground";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className={cn(
        "inline-flex items-center gap-1 rounded border px-2 py-1 disabled:opacity-50",
        className,
      )}
    >
      <Undo2 className="size-3" aria-hidden="true" />
      Discard
    </button>
  );
}

function DraftCommentRow({
  draft,
  onChange,
  onRemove,
}: {
  draft: PendingReviewComment;
  onChange: (body: string) => void;
  onRemove: () => void;
}) {
  const [open, setOpen] = useState(false);
  const range =
    draft.start_line && draft.start_line !== draft.line
      ? `${draft.start_side ?? draft.side}${draft.start_line}–${draft.side}${draft.line}`
      : `${draft.side}${draft.line}`;
  return (
    <div className="rounded-md border border-blue-200/60 bg-white/60 p-2 text-foreground dark:border-blue-900/60 dark:bg-blue-950/30">
      <header className="flex items-center justify-between gap-2 text-[11px]">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          aria-expanded={open}
          className="flex min-w-0 flex-1 items-center gap-1.5 text-left"
        >
          {open ? (
            <ChevronDown className="size-3 shrink-0" />
          ) : (
            <ChevronRight className="size-3 shrink-0" />
          )}
          <span className="truncate font-mono" title={draft.path}>
            {basename(draft.path)}
          </span>
          <span className="shrink-0 opacity-60">:{range}</span>
        </button>
        <button
          type="button"
          onClick={onRemove}
          className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
          aria-label="Remove draft comment"
          title="Remove draft"
        >
          <X className="size-3" />
        </button>
      </header>
      {open ? (
        <div className="mt-2">
          <CommentComposer
            value={draft.body}
            onChange={onChange}
            rows={3}
            compact
            placeholder="Write a review comment…"
          />
        </div>
      ) : (
        <p className="mt-1 line-clamp-2 whitespace-pre-wrap text-xs text-foreground/80">
          {draft.body || "(empty)"}
        </p>
      )}
    </div>
  );
}
