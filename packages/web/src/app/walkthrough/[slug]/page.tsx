"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { use } from "react";

import { WalkthroughLayout } from "@/components/walkthrough/walkthrough-layout";
import { api } from "@/lib/api";

export default function WalkthroughPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = use(params);
  const { data, isLoading, error } = useQuery({
    queryKey: ["walkthrough", "fixture", slug],
    queryFn: () => api.getFixture(slug),
  });

  if (isLoading) {
    return (
      <div className="flex h-screen items-center justify-center">
        <p className="text-sm text-muted-foreground">Loading walkthrough…</p>
      </div>
    );
  }

  if (error || !data) {
    return (
      <div className="flex h-screen flex-col items-center justify-center gap-3">
        <p className="text-sm text-destructive">
          {error instanceof Error ? error.message : "Failed to load fixture"}
        </p>
        <Link
          href="/repos"
          className="text-sm text-muted-foreground underline underline-offset-4 hover:text-foreground"
        >
          Back to fixtures
        </Link>
      </div>
    );
  }

  return <WalkthroughLayout walkthrough={data} slug={slug} />;
}
