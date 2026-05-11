import type {
  HunkDTO,
  ThreadDTO,
  ThreadStepDTO as ApiThreadStepDTO,
  WalkthroughDTO,
} from "@/lib/api";

export type Walkthrough = WalkthroughDTO;
export type Thread = ThreadDTO;
export type Hunk = HunkDTO;
export type ThreadStepDTO = ApiThreadStepDTO;

/**
 * Build an indexed lookup of hunks by ref ("H7" → Hunk).
 *
 * Hunks live in two places in the schema:
 *   1. Hydrated objects on each ThreadStep (when --json was emitted post-hydration)
 *   2. Bare ID references (string) in older fixtures
 *
 * We need a flat map either way so HunkView can find the full Hunk by ref.
 */
export function indexHunks(w: Walkthrough): Record<string, Hunk> {
  const index: Record<string, Hunk> = {};
  for (const thread of w.threads) {
    for (const step of thread.steps) {
      for (const ref of step.hunks) {
        if (typeof ref !== "string" && ref.id) {
          index[ref.id] = ref;
        }
      }
    }
  }
  return index;
}

export function hunkRefs(step: Thread["steps"][number]): string[] {
  return step.hunks.map((h) => (typeof h === "string" ? h : h.id));
}
