/**
 * API client. In Phase 0, the dev user is sent via X-Dev-User header.
 */

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const DEV_USER = process.env.NEXT_PUBLIC_DEV_USER ?? "alice";

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(`API ${status}: ${detail}`);
    this.status = status;
    this.detail = detail;
  }
}

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
    let detail = "";
    try {
      const body = await res.clone().json();
      detail = typeof body?.detail === "string" ? body.detail : await res.text();
    } catch {
      detail = await res.text().catch(() => "");
    }
    throw new ApiError(res.status, detail || `request to ${path} failed`);
  }
  // 204 returns no body; guard json() to avoid SyntaxError.
  if (res.status === 204) return undefined as T;
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
  getPr: (walkthroughUuid: string) =>
    request<PrDTO>(
      `/walkthroughs/${encodeURIComponent(walkthroughUuid)}/pr`,
    ),
  refreshPr: (walkthroughUuid: string) =>
    request<{ pr: PrDTO; comments: CommentDTO[] }>(
      `/walkthroughs/${encodeURIComponent(walkthroughUuid)}/pr/refresh`,
      { method: "POST" },
    ),
  listComments: (walkthroughUuid: string) =>
    request<{ comments: CommentDTO[] }>(
      `/walkthroughs/${encodeURIComponent(walkthroughUuid)}/comments`,
    ),
  createComment: (walkthroughUuid: string, body: string) =>
    request<CommentDTO>(
      `/walkthroughs/${encodeURIComponent(walkthroughUuid)}/comments`,
      {
        method: "POST",
        body: JSON.stringify({ body }),
      },
    ),
};

export type PrState = "open" | "draft" | "merged" | "closed" | null;

export interface PrDTO {
  repo: string;
  number: number;
  state: PrState;
  is_draft: boolean | null;
  title: string | null;
  body: string | null;
  html_url: string | null;
  head_sha: string | null;
  merged_at: string | null;
  closed_at: string | null;
  synced_at: string | null;
}

export type CommentKind = "issue" | "review" | "review_comment";

export interface CommentAnchor {
  path: string | null;
  line: number | null;
  side: string | null;
}

export interface CommentDTO {
  id: string;
  github_id: number | null;
  kind: CommentKind;
  author_login: string | null;
  author_avatar_url: string | null;
  body: string;
  html_url: string | null;
  anchor: CommentAnchor | null;
  review_state: string | null;
  in_reply_to_github_id: number | null;
  sync_state: "local" | "syncing" | "synced" | "failed";
  sync_error: string | null;
  created_at: string | null;
  updated_at: string | null;
}

export interface PrSourceDTO {
  repo: string;
  number: number;
  html_url: string | null;
  title: string | null;
  head_sha: string | null;
}

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
  pr?: PrSourceDTO | null;
}
