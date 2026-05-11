"use client";

import { useQueryClient } from "@tanstack/react-query";
import { Github, LogOut } from "lucide-react";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { api, githubLoginUrl } from "@/lib/api";
import { useMe } from "@/lib/use-me";

interface Props {
  next?: string;
}

export function UserMenu({ next }: Props) {
  const router = useRouter();
  const queryClient = useQueryClient();
  const { data: me, isLoading } = useMe();
  const [busy, setBusy] = useState(false);

  if (isLoading) return null;

  if (!me) {
    return (
      <a
        href={githubLoginUrl(next)}
        className="flex items-center gap-1.5 rounded px-1.5 py-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
      >
        <Github className="size-3" />
        <span>Sign in</span>
      </a>
    );
  }

  const onLogout = async () => {
    setBusy(true);
    try {
      await api.logout();
      queryClient.clear();
      router.push("/auth/login");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="flex items-center gap-2 text-muted-foreground">
      <span
        className="flex items-center gap-1.5 truncate"
        title={me.is_dev_user ? "Dev fallback user (DEV_AUTH=1)" : me.github_login}
      >
        {me.avatar_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={me.avatar_url}
            alt=""
            className="size-4 rounded-full border"
          />
        ) : (
          <Github className="size-3" />
        )}
        <span className="hidden truncate text-foreground sm:inline">
          {me.github_login}
        </span>
        {me.is_dev_user && (
          <span
            className="rounded-full bg-amber-100 px-1.5 py-px text-[9px] uppercase tracking-wider text-amber-700 dark:bg-amber-500/10 dark:text-amber-300"
            title="DEV_AUTH=1 — not a real GitHub session"
          >
            dev
          </span>
        )}
      </span>
      {!me.is_dev_user && (
        <button
          type="button"
          onClick={onLogout}
          disabled={busy}
          aria-label="Sign out"
          title="Sign out"
          className="rounded p-1 hover:bg-accent hover:text-foreground disabled:opacity-50"
        >
          <LogOut className="size-3" />
        </button>
      )}
    </div>
  );
}
