/**
 * API client. In Phase 0, the dev user is sent via X-Dev-User header.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_USER = process.env.NEXT_PUBLIC_DEV_USER ?? "alice";

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      "X-Dev-User": DEV_USER,
      ...(init.headers ?? {}),
    },
    credentials: "include",
  });
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`API ${res.status} ${path}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export const api = {
  listFixtures: () =>
    request<{ fixtures: { slug: string; path: string }[] }>(
      "/walkthroughs/fixture",
    ),
  getFixture: (slug: string) =>
    request<WalkthroughDTO>(`/walkthroughs/fixture/${encodeURIComponent(slug)}`),
  submitEdits: (walkthroughUuid: string, edits: EditPayload[]) =>
    request<BatchEditsResponse>(
      `/walkthroughs/${encodeURIComponent(walkthroughUuid)}/edits`,
      {
        method: "POST",
        body: JSON.stringify({ edits }),
      },
    ),
  getEditHistory: (walkthroughUuid: string) =>
    request<{ history: FieldEditDTO[] }>(
      `/walkthroughs/${encodeURIComponent(walkthroughUuid)}/edit-history`,
    ),
};

export type EditTargetKind = "walkthrough" | "thread" | "step";

export interface EditPayload {
  target_kind: EditTargetKind;
  target_id: string;
  field: string;
  value: string;
}

export interface FieldEditDTO {
  id: string;
  target_kind: EditTargetKind;
  target_id: string;
  field: string;
  old_value: string;
  new_value: string;
  editor: string;
  batch_id: string;
  created_at: string | null;
}

export interface BatchEditsResponse {
  walkthrough: WalkthroughDTO;
  applied: FieldEditDTO[];
}

// Mirrors the schema in src/unravel/models.py.
export interface HunkDTO {
  id: string;
  file_path: string;
  old_start: number;
  old_count: number;
  new_start: number;
  new_count: number;
  content: string;
  context_before: string;
  context_after: string;
  language: string | null;
  additions: number;
  deletions: number;
  caption: string;
}

export interface ThreadStepDTO {
  id: string;
  hunks: (HunkDTO | string)[];
  narration: string;
  order: number;
  narration_edited_at?: string | null;
}

export interface ThreadDTO {
  id: string; // LLM kebab ref — matches suggested_order entries
  uuid?: string; // DB UUID — used for future PATCH endpoints
  title: string;
  summary: string;
  root_cause: string;
  steps: ThreadStepDTO[];
  dependencies: string[];
}

export interface WalkthroughDTO {
  id?: string;
  uuid?: string;
  slug?: string;
  threads: ThreadDTO[];
  overview: string;
  suggested_order: string[];
  metadata?: Record<string, unknown>;
  hunk_captions?: Record<string, string>;
}
