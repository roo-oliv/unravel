import type { CommentDTO } from "./api";

export interface CommentThread {
  root: CommentDTO;
  replies: CommentDTO[];
}

export type PrConversationItem =
  | { kind: "issue"; comment: CommentDTO }
  | { kind: "review"; review: CommentDTO; inlineThreads: CommentThread[] }
  | { kind: "thread"; thread: CommentThread };

/**
 * Group inline review_comments into thread roots + replies.
 *
 * Roots have ``in_reply_to_github_id === null``. Replies attach to the root of
 * their parent's chain — GitHub flattens reply chains, but optimistic local
 * rows may point at a non-root parent, so we resolve transitively.
 */
export function groupReviewCommentThreads(
  reviewComments: CommentDTO[],
): CommentThread[] {
  const byGithubId = new Map<number, CommentDTO>();
  for (const c of reviewComments) {
    if (c.github_id != null) byGithubId.set(c.github_id, c);
  }

  const roots: CommentDTO[] = [];
  const repliesByRootGithubId = new Map<number, CommentDTO[]>();
  const localOrphans: CommentDTO[] = [];

  for (const c of reviewComments) {
    if (c.in_reply_to_github_id == null) {
      roots.push(c);
      continue;
    }
    // Walk up the chain to find the root.
    let cursor = byGithubId.get(c.in_reply_to_github_id);
    const seen = new Set<number>();
    while (cursor && cursor.in_reply_to_github_id != null) {
      if (cursor.github_id != null) {
        if (seen.has(cursor.github_id)) break; // cycle guard
        seen.add(cursor.github_id);
      }
      const next = byGithubId.get(cursor.in_reply_to_github_id);
      if (!next) break;
      cursor = next;
    }
    if (cursor && cursor.github_id != null) {
      const bucket = repliesByRootGithubId.get(cursor.github_id) ?? [];
      bucket.push(c);
      repliesByRootGithubId.set(cursor.github_id, bucket);
    } else {
      localOrphans.push(c);
    }
  }

  const sortByDate = (a: CommentDTO, b: CommentDTO) =>
    (a.created_at ?? "").localeCompare(b.created_at ?? "");

  roots.sort(sortByDate);
  const threads = roots.map((root) => ({
    root,
    replies: (repliesByRootGithubId.get(root.github_id!) ?? []).sort(sortByDate),
  }));

  // Promote any orphan to its own pseudo-thread (e.g. a syncing reply whose
  // parent hasn't been fetched yet) so we don't drop it on the floor.
  for (const orphan of localOrphans) {
    threads.push({ root: orphan, replies: [] });
  }

  return threads;
}

/**
 * Organise the full PR conversation into chronological items.
 *
 * - issue comments → flat items
 * - reviews → grouped with the inline threads created in the same review
 * - review_comment threads not tied to a fetched review → standalone thread items
 *
 * Returned items are sorted by `created_at` (review timestamp for reviews,
 * root timestamp for orphan threads).
 */
export function buildPrConversation(
  comments: CommentDTO[],
): PrConversationItem[] {
  const reviews = comments.filter((c) => c.kind === "review");
  const reviewById = new Map<number, CommentDTO>();
  for (const r of reviews) {
    if (r.github_id != null) reviewById.set(r.github_id, r);
  }

  const reviewComments = comments.filter((c) => c.kind === "review_comment");
  const groupedByReview = new Map<number, CommentDTO[]>();
  const orphanReviewComments: CommentDTO[] = [];
  for (const c of reviewComments) {
    const rid = c.pull_request_review_id;
    if (rid != null && reviewById.has(rid)) {
      const bucket = groupedByReview.get(rid) ?? [];
      bucket.push(c);
      groupedByReview.set(rid, bucket);
    } else {
      orphanReviewComments.push(c);
    }
  }

  const issueComments = comments.filter((c) => c.kind === "issue");

  const items: { ts: string; item: PrConversationItem }[] = [];

  for (const c of issueComments) {
    items.push({
      ts: c.created_at ?? "",
      item: { kind: "issue", comment: c },
    });
  }

  for (const r of reviews) {
    const inlineThreads = groupReviewCommentThreads(
      groupedByReview.get(r.github_id!) ?? [],
    );
    items.push({
      ts: r.created_at ?? "",
      item: { kind: "review", review: r, inlineThreads },
    });
  }

  const orphanThreads = groupReviewCommentThreads(orphanReviewComments);
  for (const t of orphanThreads) {
    items.push({
      ts: t.root.created_at ?? "",
      item: { kind: "thread", thread: t },
    });
  }

  items.sort((a, b) => a.ts.localeCompare(b.ts));
  return items.map(({ item }) => item);
}

export function basename(path: string): string {
  const i = path.lastIndexOf("/");
  return i >= 0 ? path.slice(i + 1) : path;
}

export function formatDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
