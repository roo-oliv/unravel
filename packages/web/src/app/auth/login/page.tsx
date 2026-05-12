"use client";

import { Github } from "lucide-react";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { githubLoginUrl } from "@/lib/api";

function LoginCard() {
  const params = useSearchParams();
  const error = params.get("error");
  const next = params.get("next") || "/repos";

  return (
    <main className="flex min-h-screen items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm space-y-6 rounded-xl border bg-card p-8 shadow-sm">
        <div className="space-y-2">
          <h1 className="text-2xl font-semibold tracking-tight">unravel</h1>
          <p className="text-sm text-muted-foreground">
            Sign in with GitHub to load PRs, post comments, and pick up where
            you left off.
          </p>
        </div>
        <a
          href={githubLoginUrl(next)}
          className="flex w-full items-center justify-center gap-2 rounded-md bg-foreground px-4 py-2 text-sm font-medium text-background hover:opacity-90"
        >
          <Github className="size-4" />
          Continue with GitHub
        </a>
        {error && (
          <p className="rounded-md border border-destructive/40 bg-destructive/5 p-2 text-xs text-destructive">
            {error}
          </p>
        )}
        <p className="text-[11px] leading-relaxed text-muted-foreground">
          We request{" "}
          <code className="rounded bg-muted px-1 font-mono">read:user</code>,{" "}
          <code className="rounded bg-muted px-1 font-mono">user:email</code>,
          and{" "}
          <code className="rounded bg-muted px-1 font-mono">repo</code> so
          comments are attributed to you and private PRs work. Your access
          token is encrypted at rest.
        </p>
      </div>
    </main>
  );
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginCard />
    </Suspense>
  );
}
