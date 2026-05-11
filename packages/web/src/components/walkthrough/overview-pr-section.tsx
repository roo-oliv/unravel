"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  ChevronDown,
  ChevronRight,
  ExternalLink,
  Loader2,
  MessageSquare,
} from "lucide-react";
import { useState } from "react";

import { ApiError, api, type CommentDTO } from "@/lib/api";
import {
  basename,
  buildPrConversation,
  formatDate,
  type CommentThread,
  type PrConversationItem,
} from "@/lib/comment-threads";

import { Markdown } from "./markdown";

interface Props {
  walkthroughUuid: string;
}

/**
 * Tail section of the Overview page: PR description + unified PR conversation.
 *
 * Renders a chronological feed mirroring GitHub's Conversation tab:
 *  - issue comments (top-level)
 *  - review submissions (with state badge + grouped inline threads)
 *  - orphan inline threads (rare — review_comments whose parent review is missing)
 *
 * Each inline thread shows reply chains indented with collapsed-after-3
 * behaviour and an inline reply composer. The footer composer posts a new
 * top-level issue comment to the PR.
 */
export function OverviewPrSection({ walkthroughUuid }: Props) {
  const pr = useQuery({
    queryKey: ["pr", walkthroughUuid],
    queryFn: () => api.getPr(walkthroughUuid),
    refetchInterval: 60_000,
    retry: 1,
  });
  const comments = useQuery({
    queryKey: ["comments", walkthroughUuid],
    queryFn: () => api.listComments(walkthroughUuid),
    refetchInterval: 60_000,
    retry: (failureCount, err) =>
      err instanceof ApiError && err.status === 404 ? false : failureCount < 1,
  });

  if (pr.error instanceof ApiError && pr.error.status === 404) {
    return null;
  }

  const items: PrConversationItem[] = buildPrConversation(
    comments.data?.comments ?? [],
  );
  const tokenMissing =
    comments.error instanceof ApiError && comments.error.status === 503;

  return (
    <section
      id="pr-conversation"
      className="mt-12 space-y-8 border-t pt-8"
    >
      <div>
        <header className="mb-3 flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium uppercase tracking-wide text-muted-foreground">
            Pull request
          </h2>
          {pr.data?.html_url && (
            <a
              href={pr.data.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
            >
              {pr.data.repo}#{pr.data.number}
              <ExternalLink className="size-3" />
            </a>
          )}
        </header>
        {pr.data?.title && (
          <h3 className="mb-2 text-lg font-semibold leading-tight">
            {pr.data.title}
          </h3>
        )}
        {pr.data?.body ? (
          <Markdown className="text-sm text-foreground/90">
            {pr.data.body}
          </Markdown>
        ) : (
          <p className="text-xs italic text-muted-foreground">
            {pr.isLoading
              ? "Loading PR description…"
              : "No description on this PR."}
          </p>
        )}
      </div>

      <div>
        <h2 className="mb-3 text-sm font-medium uppercase tracking-wide text-muted-foreground">
          Pull request comments
        </h2>
        {comments.isLoading && (
          <p className="text-xs text-muted-foreground">Loading conversation…</p>
        )}
        {tokenMissing && (
          <p className="text-xs italic text-muted-foreground">
            GITHUB_TOKEN not set. See .env.example.
          </p>
        )}
        {!comments.isLoading && !tokenMissing && items.length === 0 && (
          <p className="text-xs italic text-muted-foreground">
            No comments yet.
          </p>
        )}
        {items.length > 0 && (
          <ul className="space-y-4">
            {items.map((item, i) => (
              <li key={feedKey(item, i)}>
                <ConversationItem
                  item={item}
                  walkthroughUuid={walkthroughUuid}
                />
              </li>
            ))}
          </ul>
        )}

        <NewCommentComposer walkthroughUuid={walkthroughUuid} />
      </div>
    </section>
  );
}

function feedKey(item: PrConversationItem, fallback: number): string {
  if (item.kind === "issue") return `issue:${item.comment.id}`;
  if (item.kind === "review") return `review:${item.review.id}`;
  return `thread:${item.thread.root.id ?? fallback}`;
}

function ConversationItem({
  item,
  walkthroughUuid,
}: {
  item: PrConversationItem;
  walkthroughUuid: string;
}) {
  if (item.kind === "issue") {
    return <IssueCommentCard comment={item.comment} />;
  }
  if (item.kind === "review") {
    return (
      <ReviewCard
        review={item.review}
        threads={item.inlineThreads}
        walkthroughUuid={walkthroughUuid}
      />
    );
  }
  return (
    <ThreadCard thread={item.thread} walkthroughUuid={walkthroughUuid} />
  );
}

function IssueCommentCard({ comment }: { comment: CommentDTO }) {
  return (
    <article className="rounded-md border bg-background p-3 text-sm">
      <CommentHeader comment={comment} />
      <Markdown className="mt-2 text-sm">{comment.body || "_(empty)_"}</Markdown>
      <CommentFooter comment={comment} />
    </article>
  );
}

function ReviewCard({
  review,
  threads,
  walkthroughUuid,
}: {
  review: CommentDTO;
  threads: CommentThread[];
  walkthroughUuid: string;
}) {
  const [expanded, setExpanded] = useState(threads.length <= 2);
  const inlineCount = threads.reduce(
    (n, t) => n + 1 + t.replies.length,
    0,
  );
  const fileCount = new Set(
    threads.map((t) => t.root.anchor?.path ?? "?"),
  ).size;

  return (
    <article className="rounded-md border bg-background p-3 text-sm">
      <CommentHeader comment={review} stateBadge />
      {review.body.trim() ? (
        <Markdown className="mt-2 text-sm">{review.body}</Markdown>
      ) : (
        <p className="mt-2 text-xs italic text-muted-foreground">
          {reviewStateSummary(review.review_state)}
        </p>
      )}
      <CommentFooter comment={review} />
      {threads.length > 0 && (
        <div className="mt-3 border-t pt-3">
          <button
            type="button"
            onClick={() => setExpanded((e) => !e)}
            className="flex items-center gap-1.5 text-xs text-muted-foreground hover:text-foreground"
            aria-expanded={expanded}
          >
            {expanded ? (
              <ChevronDown className="size-3" />
            ) : (
              <ChevronRight className="size-3" />
            )}
            <MessageSquare className="size-3" />
            {inlineCount} inline {inlineCount === 1 ? "comment" : "comments"}{" "}
            on {fileCount} {fileCount === 1 ? "file" : "files"}
          </button>
          {expanded && (
            <ul className="mt-3 space-y-3">
              {threads.map((t) => (
                <li key={t.root.id}>
                  <ThreadCard
                    thread={t}
                    walkthroughUuid={walkthroughUuid}
                    nested
                  />
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </article>
  );
}

function reviewStateSummary(state: string | null): string {
  if (!state) return "Submitted a review.";
  const norm = state.toUpperCase();
  if (norm === "APPROVED") return "Approved these changes.";
  if (norm === "CHANGES_REQUESTED") return "Requested changes.";
  if (norm === "COMMENTED") return "Left a review.";
  return state.toLowerCase().replace(/_/g, " ");
}

function ThreadCard({
  thread,
  walkthroughUuid,
  nested = false,
}: {
  thread: CommentThread;
  walkthroughUuid: string;
  nested?: boolean;
}) {
  return (
    <div
      className={
        nested
          ? "rounded-md border bg-muted/20 p-2.5 text-xs"
          : "rounded-md border bg-background p-3 text-sm"
      }
    >
      {thread.root.anchor?.path && (
        <div className="mb-2 flex items-center gap-1.5 font-mono text-[11px] text-muted-foreground">
          <span className="truncate" title={thread.root.anchor.path}>
            {basename(thread.root.anchor.path)}
          </span>
          <span className="opacity-60">
            :{thread.root.anchor.line ?? "?"}
          </span>
        </div>
      )}
      <ThreadComment comment={thread.root} />
      <ThreadReplies
        replies={thread.replies}
        walkthroughUuid={walkthroughUuid}
        parentId={thread.root.id}
      />
    </div>
  );
}

const REPLY_PREVIEW_LIMIT = 3;

function ThreadReplies({
  replies,
  walkthroughUuid,
  parentId,
}: {
  replies: CommentDTO[];
  walkthroughUuid: string;
  parentId: string;
}) {
  const [showAll, setShowAll] = useState(replies.length <= REPLY_PREVIEW_LIMIT);
  const visible = showAll ? replies : replies.slice(-REPLY_PREVIEW_LIMIT);
  const hidden = replies.length - visible.length;

  return (
    <div className="mt-2 space-y-2 border-l-2 border-muted pl-3">
      {hidden > 0 && (
        <button
          type="button"
          onClick={() => setShowAll(true)}
          className="text-[11px] text-muted-foreground hover:text-foreground"
        >
          Show {hidden} earlier {hidden === 1 ? "reply" : "replies"}
        </button>
      )}
      {visible.map((reply) => (
        <ThreadComment key={reply.id} comment={reply} compact />
      ))}
      <ReplyComposer
        walkthroughUuid={walkthroughUuid}
        parentCommentId={parentId}
      />
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
      <CommentHeader comment={comment} small={compact} />
      <Markdown className={compact ? "mt-1 text-xs" : "mt-1.5 text-sm"}>
        {comment.body || "_(empty)_"}
      </Markdown>
      {comment.created_at && (
        <time className="mt-1 block text-[10px] text-muted-foreground">
          {formatDate(comment.created_at)}
        </time>
      )}
    </div>
  );
}

function CommentHeader({
  comment,
  small = false,
  stateBadge = false,
}: {
  comment: CommentDTO;
  small?: boolean;
  stateBadge?: boolean;
}) {
  return (
    <header className="flex items-center justify-between gap-2">
      <div className="flex min-w-0 items-center gap-1.5">
        {comment.author_avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={comment.author_avatar_url}
            alt=""
            className={small ? "size-4 rounded-full" : "size-5 rounded-full"}
          />
        ) : null}
        <span
          className={
            small
              ? "truncate text-xs font-medium"
              : "truncate text-sm font-medium"
          }
        >
          {comment.author_login ?? "unknown"}
        </span>
        {stateBadge && comment.review_state && (
          <StateBadge state={comment.review_state} />
        )}
        <SyncStateBadge comment={comment} />
      </div>
      {comment.html_url && (
        <a
          href={comment.html_url}
          target="_blank"
          rel="noopener noreferrer"
          className="shrink-0 text-muted-foreground hover:text-foreground"
          title="Open on GitHub"
        >
          <ExternalLink className="size-3" />
        </a>
      )}
    </header>
  );
}

function CommentFooter({ comment }: { comment: CommentDTO }) {
  if (!comment.created_at) return null;
  return (
    <time className="mt-2 block text-[10px] text-muted-foreground">
      {formatDate(comment.created_at)}
    </time>
  );
}

function StateBadge({ state }: { state: string }) {
  const norm = state.toUpperCase();
  const cls =
    norm === "APPROVED"
      ? "bg-emerald-100 text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300"
      : norm === "CHANGES_REQUESTED"
        ? "bg-rose-100 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300"
        : "bg-muted text-foreground/70";
  return (
    <span
      className={`rounded-full px-1.5 py-px text-[9px] uppercase tracking-wider ${cls}`}
    >
      {state.toLowerCase().replace(/_/g, " ")}
    </span>
  );
}

function SyncStateBadge({ comment }: { comment: CommentDTO }) {
  if (comment.sync_state === "syncing" || comment.sync_state === "local") {
    return (
      <span className="rounded-full bg-amber-100 px-1.5 py-px text-[9px] uppercase tracking-wider text-amber-700 dark:bg-amber-500/10 dark:text-amber-300">
        syncing
      </span>
    );
  }
  if (comment.sync_state === "failed") {
    return (
      <span
        className="rounded-full bg-rose-100 px-1.5 py-px text-[9px] uppercase tracking-wider text-rose-700 dark:bg-rose-500/10 dark:text-rose-300"
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

  return (
    <form
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
        rows={2}
        autoFocus
        placeholder="Reply (Markdown)…"
        className="w-full resize-y rounded-md border bg-background px-2 py-1.5 text-xs leading-relaxed focus:border-foreground/40 focus:outline-none"
        disabled={submit.isPending}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
            e.preventDefault();
            const value = draft.trim();
            if (value && !submit.isPending) submit.mutate(value);
          }
          if (e.key === "Escape") {
            e.preventDefault();
            setOpen(false);
            setDraft("");
          }
        }}
      />
      <div className="mt-1.5 flex items-center justify-between gap-2">
        <span className="text-[10px] text-muted-foreground">
          ⌘↵ to send · esc to cancel
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              setOpen(false);
              setDraft("");
            }}
            className="text-[11px] text-muted-foreground hover:text-foreground"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!draft.trim() || submit.isPending}
            className="inline-flex items-center gap-1.5 rounded-md bg-foreground px-2 py-1 text-[11px] font-medium text-background disabled:cursor-not-allowed disabled:opacity-50"
          >
            {submit.isPending ? <Loader2 className="size-3 animate-spin" /> : null}
            {submit.isPending ? "Sending…" : "Reply"}
          </button>
        </div>
      </div>
      {submit.error && (
        <p className="mt-1 flex items-center gap-1 text-[11px] text-destructive">
          <AlertCircle className="size-3" />
          {(submit.error as Error).message}
        </p>
      )}
    </form>
  );
}

function NewCommentComposer({
  walkthroughUuid,
}: {
  walkthroughUuid: string;
}) {
  const queryClient = useQueryClient();
  const [draft, setDraft] = useState("");

  const submit = useMutation({
    mutationFn: (body: string) =>
      api.createComment(walkthroughUuid, body),
    onSuccess: () => {
      setDraft("");
      queryClient.invalidateQueries({
        queryKey: ["comments", walkthroughUuid],
      });
    },
  });

  return (
    <form
      className="mt-6 rounded-md border bg-background p-3"
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
        disabled={submit.isPending}
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
          disabled={!draft.trim() || submit.isPending}
          className="inline-flex items-center gap-1.5 rounded-md bg-foreground px-2.5 py-1 text-xs font-medium text-background disabled:cursor-not-allowed disabled:opacity-50"
        >
          {submit.isPending ? <Loader2 className="size-3 animate-spin" /> : null}
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
  );
}
