"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import type { ReviewCommentPayload } from "@/lib/api";

export interface PendingReviewComment {
  /** Stable client-side id so the UI can render + edit/remove individual drafts. */
  id: string;
  path: string;
  line: number;
  side: "LEFT" | "RIGHT";
  start_line: number | null;
  start_side: "LEFT" | "RIGHT" | null;
  body: string;
  stagedAt: string; // ISO
}

export interface PendingReview {
  /** Optional review summary body (rendered at top of the bar). */
  summary: string;
  comments: PendingReviewComment[];
}

interface PendingReviewState {
  // walkthroughUuid → review draft
  drafts: Record<string, PendingReview>;
  addComment(walkthroughUuid: string, draft: PendingReviewComment): void;
  updateComment(
    walkthroughUuid: string,
    id: string,
    patch: Partial<Pick<PendingReviewComment, "body">>,
  ): void;
  removeComment(walkthroughUuid: string, id: string): void;
  setSummary(walkthroughUuid: string, body: string): void;
  clear(walkthroughUuid: string): void;
}

function emptyDraft(): PendingReview {
  return { summary: "", comments: [] };
}

/**
 * In-flight review draft (zero or more inline comments + an optional summary).
 *
 * Persisted to localStorage so a refresh doesn't drop a pending review.
 * Submission is owned by the bar component — this store is purely state.
 */
export const usePendingReviewStore = create<PendingReviewState>()(
  persist(
    (set) => ({
      drafts: {},
      addComment: (walkthroughUuid, draft) =>
        set((state) => {
          const cur = state.drafts[walkthroughUuid] ?? emptyDraft();
          return {
            drafts: {
              ...state.drafts,
              [walkthroughUuid]: {
                ...cur,
                comments: [...cur.comments, draft],
              },
            },
          };
        }),
      updateComment: (walkthroughUuid, id, patch) =>
        set((state) => {
          const cur = state.drafts[walkthroughUuid];
          if (!cur) return state;
          return {
            drafts: {
              ...state.drafts,
              [walkthroughUuid]: {
                ...cur,
                comments: cur.comments.map((c) =>
                  c.id === id ? { ...c, ...patch } : c,
                ),
              },
            },
          };
        }),
      removeComment: (walkthroughUuid, id) =>
        set((state) => {
          const cur = state.drafts[walkthroughUuid];
          if (!cur) return state;
          const remaining = cur.comments.filter((c) => c.id !== id);
          // Drop the draft entirely when the last inline is gone — the bar
          // only renders for comment-bearing drafts, so a lingering summary
          // would silently survive in localStorage.
          if (remaining.length === 0) {
            const next = { ...state.drafts };
            delete next[walkthroughUuid];
            return { drafts: next };
          }
          return {
            drafts: {
              ...state.drafts,
              [walkthroughUuid]: { ...cur, comments: remaining },
            },
          };
        }),
      setSummary: (walkthroughUuid, body) =>
        set((state) => {
          const cur = state.drafts[walkthroughUuid];
          if (!cur && !body) return state;
          const next = cur ?? emptyDraft();
          if (!body && next.comments.length === 0) {
            const drafts = { ...state.drafts };
            delete drafts[walkthroughUuid];
            return { drafts };
          }
          return {
            drafts: {
              ...state.drafts,
              [walkthroughUuid]: { ...next, summary: body },
            },
          };
        }),
      clear: (walkthroughUuid) =>
        set((state) => {
          if (!(walkthroughUuid in state.drafts)) return state;
          const drafts = { ...state.drafts };
          delete drafts[walkthroughUuid];
          return { drafts };
        }),
    }),
    {
      name: "unravel:pending-review:v1",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);

export function toReviewCommentPayloads(
  draft: PendingReview,
): ReviewCommentPayload[] {
  return draft.comments.map((c) => ({
    body: c.body,
    path: c.path,
    line: c.line,
    side: c.side,
    start_line: c.start_line,
    start_side: c.start_side,
  }));
}

export function newPendingId(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `pr-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
