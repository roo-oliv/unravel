"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, Send, Undo2 } from "lucide-react";

import { api, type WalkthroughDTO } from "@/lib/api";
import {
  toEditPayloads,
  usePendingEditsStore,
} from "@/lib/pending-edits";

interface Props {
  walkthroughUuid: string;
  slug?: string;
}

/**
 * Top-of-page indicator + global controls for unsaved edits.
 *
 * Render this in the layout grid as an auto-height row that collapses to
 * height 0 when there are no pending edits — the parent layout already wires
 * the row, this component returns null when empty.
 */
export function PendingEditsBar({ walkthroughUuid, slug }: Props) {
  // Subscribe to the (possibly undefined) per-walkthrough map directly so the
  // reference is stable across renders — returning `?? {}` here would mint a
  // new object each render and trip Zustand's useSyncExternalStore guard.
  const editsMap = usePendingEditsStore(
    (s) => s.edits[walkthroughUuid],
  );
  const clearWalkthrough = usePendingEditsStore((s) => s.clearWalkthrough);
  const queryClient = useQueryClient();

  const count = editsMap ? Object.keys(editsMap).length : 0;

  const submitMutation = useMutation({
    mutationFn: () =>
      api.submitEdits(walkthroughUuid, toEditPayloads(editsMap ?? {})),
    onSuccess: (data) => {
      clearWalkthrough(walkthroughUuid);
      if (slug) {
        queryClient.setQueryData<WalkthroughDTO | undefined>(
          ["walkthrough", "fixture", slug],
          data.walkthrough,
        );
      }
      queryClient.invalidateQueries({
        queryKey: ["edit-history", walkthroughUuid],
      });
    },
  });

  if (count === 0) return null;

  const handleSubmit = () => {
    if (submitMutation.isPending) return;
    submitMutation.mutate();
  };

  const handleCancel = () => {
    if (submitMutation.isPending) return;
    const ok = window.confirm(
      `Discard ${count} unsaved edit${count === 1 ? "" : "s"}? This can't be undone.`,
    );
    if (!ok) return;
    clearWalkthrough(walkthroughUuid);
  };

  return (
    <div
      role="region"
      aria-label="Unsaved edits"
      className="flex items-center justify-between gap-3 border-b border-amber-200 bg-amber-50 px-4 py-1.5 text-xs text-amber-900 dark:border-amber-900/60 dark:bg-amber-950/40 dark:text-amber-200"
    >
      <div className="flex items-center gap-2">
        <span className="font-medium tabular-nums">
          {count} unsaved edit{count === 1 ? "" : "s"}
        </span>
        <span className="hidden text-amber-800/70 sm:inline dark:text-amber-300/70">
          · stored in this browser until submitted
        </span>
        {submitMutation.error && (
          <span className="text-destructive">
            · submit failed: {(submitMutation.error as Error).message}
          </span>
        )}
      </div>
      <div className="flex items-center gap-2">
        <button
          type="button"
          onClick={handleCancel}
          disabled={submitMutation.isPending}
          className="inline-flex items-center gap-1 rounded border border-amber-300 bg-white/60 px-2 py-1 text-amber-900 hover:bg-white disabled:opacity-50 dark:border-amber-800 dark:bg-amber-900/40 dark:text-amber-100 dark:hover:bg-amber-900/60"
        >
          <Undo2 className="size-3" aria-hidden="true" />
          Cancel
        </button>
        <button
          type="button"
          onClick={handleSubmit}
          disabled={submitMutation.isPending}
          className="inline-flex items-center gap-1 rounded bg-amber-600 px-2 py-1 font-medium text-white hover:bg-amber-700 disabled:opacity-50 dark:bg-amber-500 dark:hover:bg-amber-400 dark:text-amber-950"
        >
          {submitMutation.isPending ? (
            <Loader2 className="size-3 animate-spin" aria-hidden="true" />
          ) : (
            <Send className="size-3" aria-hidden="true" />
          )}
          Submit edits
        </button>
      </div>
    </div>
  );
}
