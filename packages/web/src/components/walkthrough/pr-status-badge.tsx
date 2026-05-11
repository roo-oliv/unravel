"use client";

import { useQuery } from "@tanstack/react-query";
import { ExternalLink, GitMerge, GitPullRequest, GitPullRequestClosed, GitPullRequestDraft } from "lucide-react";

import { api, type PrDTO } from "@/lib/api";

interface Props {
  walkthroughUuid: string;
  fallbackHref?: string | null;
}

/**
 * Status pill that polls the cached PR snapshot every 60s.
 *
 * Renders nothing while the walkthrough has no associated PR (404 from the
 * API) — that's the dev/fixture case where we never persisted a source.
 */
export function PrStatusBadge({ walkthroughUuid, fallbackHref }: Props) {
  const { data, error } = useQuery({
    queryKey: ["pr", walkthroughUuid],
    queryFn: () => api.getPr(walkthroughUuid),
    refetchInterval: 60_000,
    refetchOnWindowFocus: true,
    retry: 1,
  });

  const href = data?.html_url ?? fallbackHref ?? null;

  if (error) {
    return null;
  }
  if (!data) {
    return null;
  }

  const state = (data.is_draft ? "draft" : data.state) ?? "unknown";
  const style = STATE_STYLES[state] ?? STATE_STYLES.unknown;
  const Icon = style.icon;

  const content = (
    <span
      className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium uppercase tracking-wide ${style.className}`}
      title={tooltipFor(data)}
    >
      <Icon className="size-3" />
      {style.label}
    </span>
  );

  if (!href) return content;
  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      className="inline-flex items-center gap-1 hover:opacity-80"
    >
      {content}
      <ExternalLink className="size-3 text-muted-foreground" />
    </a>
  );
}

const STATE_STYLES: Record<
  string,
  { label: string; className: string; icon: typeof GitPullRequest }
> = {
  open: {
    label: "open",
    className:
      "border-emerald-300 bg-emerald-100 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-500/10 dark:text-emerald-300",
    icon: GitPullRequest,
  },
  draft: {
    label: "draft",
    className:
      "border-slate-300 bg-slate-100 text-slate-600 dark:border-slate-500/40 dark:bg-slate-500/10 dark:text-slate-300",
    icon: GitPullRequestDraft,
  },
  merged: {
    label: "merged",
    className:
      "border-purple-300 bg-purple-100 text-purple-700 dark:border-purple-500/40 dark:bg-purple-500/10 dark:text-purple-300",
    icon: GitMerge,
  },
  closed: {
    label: "closed",
    className:
      "border-rose-300 bg-rose-100 text-rose-700 dark:border-rose-500/40 dark:bg-rose-500/10 dark:text-rose-300",
    icon: GitPullRequestClosed,
  },
  unknown: {
    label: "unknown",
    className:
      "border-amber-300 bg-amber-100 text-amber-700 dark:border-amber-500/40 dark:bg-amber-500/10 dark:text-amber-300",
    icon: GitPullRequest,
  },
};

function tooltipFor(pr: PrDTO): string {
  const parts: string[] = [];
  if (pr.title) parts.push(pr.title);
  if (pr.merged_at) parts.push(`merged ${pr.merged_at.slice(0, 10)}`);
  else if (pr.closed_at) parts.push(`closed ${pr.closed_at.slice(0, 10)}`);
  if (pr.synced_at) parts.push(`synced ${pr.synced_at.slice(0, 16).replace("T", " ")}`);
  else parts.push("not synced yet — set GITHUB_TOKEN in .env");
  return parts.join(" · ");
}
