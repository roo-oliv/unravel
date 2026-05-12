import type { HunkDTO } from "@/lib/api";

function distanceToHunk(h: HunkDTO, line: number): number {
  const start = h.new_start;
  const end = h.new_start + Math.max(h.new_count, 1) - 1;
  if (line < start) return start - line;
  if (line > end) return line - end;
  return 0;
}

/**
 * Decide if ``hunk`` should host a comment anchored at ``line`` against the
 * set of ``siblings`` (every hunk that touches the same file inside the same
 * thread). The rule: pick the hunk closest to the line; ties broken by the
 * smallest ``new_start``, then by ``id`` for stability.
 */
export function ownsLine(
  hunk: HunkDTO,
  siblings: HunkDTO[],
  line: number,
): boolean {
  if (siblings.length <= 1) return true;
  const myDist = distanceToHunk(hunk, line);
  const minDist = siblings.reduce(
    (m, s) => Math.min(m, distanceToHunk(s, line)),
    Number.POSITIVE_INFINITY,
  );
  if (myDist !== minDist) return false;
  const tied = siblings.filter((s) => distanceToHunk(s, line) === minDist);
  if (tied.length === 1) return true;
  tied.sort((a, b) => a.new_start - b.new_start || a.id.localeCompare(b.id));
  return tied[0].id === hunk.id;
}
