"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertCircle, ExternalLink, Loader2, RefreshCw, X } from "lucide-react";
import { memo, useState } from "react";

import { ApiError, api, type CommentDTO } from "@/lib/api";

import { Markdown } from "./markdown";

interface Props {
  walkthroughUuid: string;
  open: boolean;
  onClose: () => void;
  /**
   * When set, scopes the comment list to those anchored at `path` (any line)
   * — used when a thread is active. Top-level issue comments are always shown
   * in addition; review summaries surface in the Overview block instead.
   */
  filterPath?: string | null;
}

/**
 * Right-side comments column. Reads `/walkthroughs/:uuid/comments` and shows
 * issue comments first, then review_comments (line-anchored). The compose form
 * always creates a top-level issue comment for now — line-anchored writes need
 * a head SHA + position calculation that we'll add in a follow-up.
 */
export function CommentsDrawer({
  walkthroughUuid,
  open,
  onClose,
  filterPath,
}: Props) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");

  const { data, error, isLoading, isFetching, refetch } = useQuery({
    queryKey: ["comments", walkthroughUuid],
    queryFn: () => api.listComments(walkthroughUuid),
    refetchInterval: open ? 30_000 : false,
    enabled: open,
    retry: (failureCount, err) =>
      err instanceof ApiError && err.status === 404 ? false : failureCount < 1,
  });

  const refresh = useMutation({
    mutationFn: () => api.refreshPr(walkthroughUuid),
    onSuccess: (resp) => {
      queryClient.setQueryData(["comments", walkthroughUuid], {
        comments: resp.comments,
      });
      queryClient.setQueryData(["pr", walkthroughUuid], resp.pr);
    },
  });

  const submit = useMutation({
    mutationFn: (body: string) => api.createComment(walkthroughUuid, body),
    onSuccess: () => {
      setDraft("");
      queryClient.invalidateQueries({ queryKey: ["comments", walkthroughUuid] });
    },
  });

  if (!open) return null;

  const all = data?.comments ?? [];
  const issueComments = all.filter((c) => c.kind === "issue");
  const reviewComments = all.filter((c) => c.kind === "review_comment");
  const filteredReview = filterPath
    ? reviewComments.filter((c) => c.anchor?.path === filterPath)
    : reviewComments;

  const noPr =
    error instanceof ApiError && error.status === 404;
  const tokenMissing =
    error instanceof ApiError && error.status === 503;

  return (
    <aside className="flex h-full min-h-0 w-[360px] shrink-0 flex-col border-l bg-muted/15">
      <header className="flex items-center justify-between border-b px-3 py-2">
        <div className="flex items-center gap-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
          Comments
          {all.length > 0 && (
            <span className="rounded-full bg-muted px-1.5 py-0.5 text-[10px] text-foreground/70">
              {all.length}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => refresh.mutate()}
            disabled={refresh.isPending || isFetching}
            aria-label="Refresh from GitHub"
            title="Refresh from GitHub"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
          >
            <RefreshCw
              className={`size-3.5 ${refresh.isPending || isFetching ? "animate-spin" : ""}`}
            />
          </button>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close comments"
            title="Close (d)"
            className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
          >
            <X className="size-3.5" />
          </button>
        </div>
      </header>

      <div className="flex-1 overflow-y-auto px-3 py-3">
        {isLoading && (
          <p className="text-xs text-muted-foreground">Loading comments…</p>
        )}
        {noPr && (
          <EmptyState
            title="No GitHub PR linked"
            body="This walkthrough was generated without source metadata. Regenerate the fixture with the latest CLI to enable comments."
          />
        )}
        {tokenMissing && (
          <EmptyState
            title="GITHUB_TOKEN not set"
            body="Set a GitHub PAT in your .env to fetch and post PR comments. See .env.example."
          />
        )}
        {!noPr && !tokenMissing && error && (
          <EmptyState
            title="Failed to load"
            body={(error as Error).message}
          />
        )}

        {!error && (issueComments.length > 0 || filteredReview.length > 0) ? (
          <ul className="space-y-3">
            {issueComments.map((c) => (
              <li key={c.id}>
                <CommentCard comment={c} />
              </li>
            ))}
            {filteredReview.length > 0 && (
              <li className="pt-2">
                <h4 className="mb-2 text-[10px] font-medium uppercase tracking-wider text-muted-foreground">
                  {filterPath
                    ? `Inline · ${filterPath}`
                    : "Inline review"}
                </h4>
                <ul className="space-y-3">
                  {filteredReview.map((c) => (
                    <li key={c.id}>
                      <CommentCard comment={c} />
                    </li>
                  ))}
                </ul>
              </li>
            )}
          </ul>
        ) : null}

        {!error && !isLoading && all.length === 0 && (
          <p className="text-xs text-muted-foreground">
            No comments yet. Be the first to say something on this PR.
          </p>
        )}
      </div>

      <form
        className="border-t bg-background/60 p-3"
        onSubmit={(e) => {
          e.preventDefault();
          const value = draft.trim();
          if (!value || submit.isPending) return;
          submit.mutate(value);
        }}
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          placeholder="Write a PR comment (Markdown)…"
          className="w-full resize-y rounded-md border bg-background px-2 py-1.5 text-xs leading-relaxed focus:border-foreground/40 focus:outline-none"
          disabled={submit.isPending || noPr || tokenMissing}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              const value = draft.trim();
              if (value && !submit.isPending) submit.mutate(value);
            }
          }}
        />
        <div className="mt-2 flex items-center justify-between gap-2">
          <span className="text-[10px] text-muted-foreground">
            ⌘↵ to send · posts to GitHub
          </span>
          <button
            type="submit"
            disabled={!draft.trim() || submit.isPending || noPr || tokenMissing}
            className="inline-flex items-center gap-1.5 rounded-md bg-foreground px-2.5 py-1 text-xs font-medium text-background disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submit.isPending ? (
              <Loader2 className="size-3 animate-spin" />
            ) : null}
            {submit.isPending ? "Sending…" : "Comment"}
          </button>
        </div>
        {submit.error && (
          <p className="mt-2 flex items-center gap-1 text-[11px] text-destructive">
            <AlertCircle className="size-3" />
            {(submit.error as Error).message}
          </p>
        )}
      </form>
    </aside>
  );
}

function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="rounded-md border border-dashed p-3 text-xs">
      <p className="font-medium">{title}</p>
      <p className="mt-1 text-muted-foreground">{body}</p>
    </div>
  );
}

const CommentCard = memo(function CommentCard({
  comment,
}: {
  comment: CommentDTO;
}) {
  const stateBadge =
    comment.sync_state === "syncing" || comment.sync_state === "local" ? (
      <span className="rounded-full bg-amber-100 px-1.5 py-px text-[9px] uppercase tracking-wider text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
        syncing
      </span>
    ) : comment.sync_state === "failed" ? (
      <span
        className="rounded-full bg-rose-100 px-1.5 py-px text-[9px] uppercase tracking-wider text-rose-700 dark:bg-rose-500/10 dark:text-rose-300"
        title={comment.sync_error ?? undefined}
      >
        failed
      </span>
    ) : null;

  return (
    <article className="rounded-md border bg-background p-2.5 text-xs">
      <header className="mb-1.5 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-1.5">
          {comment.author_avatar_url ? (
            // GitHub avatars are tiny + cached aggressively.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={comment.author_avatar_url}
              alt=""
              className="size-4 rounded-full"
            />
          ) : null}
          <span className="truncate font-medium">
            {comment.author_login ?? "unknown"}
          </span>
          {comment.kind === "review_comment" && comment.anchor?.path && (
            <span
              className="truncate font-mono text-[10px] text-muted-foreground"
              title={`${comment.anchor.path}:${comment.anchor.line ?? "?"}`}
            >
              {basename(comment.anchor.path)}:
              {comment.anchor.line ?? "?"}
            </span>
          )}
          {comment.review_state && comment.review_state !== "COMMENTED" && (
            <span className="rounded-full bg-muted px-1.5 py-px text-[9px] uppercase tracking-wider text-foreground/70">
              {comment.review_state.toLowerCase().replace("_", " ")}
            </span>
          )}
        </div>
        <div className="flex items-center gap-1">
          {stateBadge}
          {comment.html_url && (
            <a
              href={comment.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-muted-foreground hover:text-foreground"
              title="Open on GitHub"
            >
              <ExternalLink className="size-3" />
            </a>
          )}
        </div>
      </header>
      <Markdown className="text-xs">{comment.body || "_(empty)_"}</Markdown>
      {comment.created_at && (
        <time className="mt-1.5 block text-[10px] text-muted-foreground">
          {formatDate(comment.created_at)}
        </time>
      )}
    </article>
  );
});

function basename(path: string): string {
  const i = path.lastIndexOf("/");
  return i >= 0 ? path.slice(i + 1) : path;
}

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
