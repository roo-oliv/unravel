"use client";

import { create } from "zustand";

/**
 * "Viewed" hunk marks, keyed per walkthrough slug.
 *
 * The server is the source of truth (Postgres ``hunk_viewed`` table, anchored
 * on the logged-in user). This store is just a fast local cache for the
 * current page so toggles feel instant; reconciliation happens via the POST
 * response, which returns the canonical set.
 *
 * Anonymous / dev users have no DB row, so the store stays empty and the
 * checkbox is hidden — see the gate in HunkView.
 */
interface ViewedHunksState {
  /** slug → Set of viewed content_hashes. Set, not array, so toggles are O(1). */
  bySlug: Record<string, Set<string>>;
  hydrate(slug: string, hashes: string[]): void;
  set(slug: string, hashes: string[]): void;
  toggleOptimistic(slug: string, hash: string, viewed: boolean): void;
  isViewed(slug: string, hash: string): boolean;
  hashesFor(slug: string): Set<string>;
}

const EMPTY: Set<string> = new Set();

export const useViewedHunksStore = create<ViewedHunksState>()((set, get) => ({
  bySlug: {},
  hydrate: (slug, hashes) =>
    set((state) => ({
      bySlug: { ...state.bySlug, [slug]: new Set(hashes) },
    })),
  set: (slug, hashes) =>
    set((state) => ({
      bySlug: { ...state.bySlug, [slug]: new Set(hashes) },
    })),
  toggleOptimistic: (slug, hash, viewed) =>
    set((state) => {
      const cur = new Set(state.bySlug[slug] ?? []);
      if (viewed) cur.add(hash);
      else cur.delete(hash);
      return { bySlug: { ...state.bySlug, [slug]: cur } };
    }),
  isViewed: (slug, hash) => {
    if (!hash) return false;
    return get().bySlug[slug]?.has(hash) ?? false;
  },
  hashesFor: (slug) => get().bySlug[slug] ?? EMPTY,
}));
