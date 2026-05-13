"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";

import { ThemePaletteButton } from "@/components/theme/theme-palette-button";
import { UserMenu } from "@/components/user-menu";
import { api } from "@/lib/api";

export default function ReposPage() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["fixtures"],
    queryFn: api.listFixtures,
  });

  return (
    <main className="container max-w-4xl py-12">
      <header className="mb-8 flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">
            Walkthrough fixtures
          </h1>
          <p className="text-sm text-muted-foreground mt-1">
            Phase 0 dev. Drop walkthrough JSON files in{" "}
            <code className="font-mono text-xs px-1 py-0.5 rounded bg-muted">
              fixtures/
            </code>{" "}
            and they show up here.
          </p>
        </div>
        <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
          <ThemePaletteButton />
          <UserMenu next="/repos" />
        </div>
      </header>

      {isLoading && (
        <p className="text-sm text-muted-foreground">Loading…</p>
      )}
      {error && (
        <p className="text-sm text-destructive">
          Failed to load fixtures: {(error as Error).message}
        </p>
      )}
      {data && data.fixtures.length === 0 && (
        <div className="rounded-lg border border-dashed p-8 text-center">
          <p className="text-sm text-muted-foreground">
            No fixtures yet. Generate one with:
          </p>
          <pre className="mt-3 inline-block rounded bg-muted px-3 py-2 text-xs font-mono">
            unravel pr 42 --json &gt; fixtures/myrepo-pr-42.json
          </pre>
        </div>
      )}
      {data && data.fixtures.length > 0 && (
        <ul className="divide-y divide-border rounded-lg border">
          {data.fixtures.map((f) => (
            <li key={f.slug}>
              <Link
                href={`/walkthrough/${encodeURIComponent(f.slug)}`}
                className="flex items-center justify-between px-4 py-3 hover:bg-accent transition-colors"
              >
                <span className="font-mono text-sm">{f.slug}</span>
                <span className="text-xs text-muted-foreground">
                  {f.path}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}
