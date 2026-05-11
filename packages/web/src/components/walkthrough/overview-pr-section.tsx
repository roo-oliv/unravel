"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink } from "lucide-react";

import { ApiError, api, type CommentDTO } from "@/lib/api";

import { Markdown } from "./markdown";

interface Props {
  walkthroughUuid: string;
}

/**
 * Tail section of the Overview page: PR description + PR-level reviews.
 *
 * Splits cleanly from the comments drawer because the data scope is different:
 *  - description: one-time read of ``GET /pr``
 *  - reviews: filter the comments list by ``kind === "review"`` (PR-wide
 *    feedback that doesn't belong against a single thread/hunk)
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

  const reviews = (comments.data?.comments ?? []).filter(
    (c) => c.kind === "review" && (c.body ?? "").trim().length > 0,
  );

  return (
    <section className="mt-12 space-y-8 border-t pt-8">
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
          Review comments
        </h2>
        {comments.isLoading && (
          <p className="text-xs text-muted-foreground">Loading reviews…</p>
        )}
        {!comments.isLoading && reviews.length === 0 && (
          <p className="text-xs italic text-muted-foreground">
            No PR-wide reviews yet.
          </p>
        )}
        {reviews.length > 0 && (
          <ul className="space-y-3">
            {reviews.map((r) => (
              <li key={r.id}>
                <ReviewCard review={r} />
              </li>
            ))}
          </ul>
        )}
      </div>
    </section>
  );
}

function ReviewCard({ review }: { review: CommentDTO }) {
  return (
    <article className="rounded-md border bg-background p-3 text-sm">
      <header className="mb-2 flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          {review.author_avatar_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={review.author_avatar_url}
              alt=""
              className="size-5 rounded-full"
            />
          ) : null}
          <span className="truncate font-medium">
            {review.author_login ?? "unknown"}
          </span>
          {review.review_state && (
            <span className="rounded-full bg-muted px-1.5 py-px text-[10px] uppercase tracking-wider text-foreground/70">
              {review.review_state.toLowerCase().replace(/_/g, " ")}
            </span>
          )}
        </div>
        {review.html_url && (
          <a
            href={review.html_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-muted-foreground hover:text-foreground"
          >
            <ExternalLink className="size-3" />
          </a>
        )}
      </header>
      <Markdown className="text-sm">{review.body}</Markdown>
    </article>
  );
}
