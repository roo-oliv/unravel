"use client";

import { useEffect } from "react";

import { useUiSettings } from "@/lib/ui-settings";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function SettingsDialog({ open, onOpenChange }: Props) {
  const fullWidth = useUiSettings((s) => s.fullWidth);
  const setFullWidth = useUiSettings((s) => s.setFullWidth);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        onOpenChange(false);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onOpenChange]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Display settings"
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      <button
        type="button"
        aria-label="Close settings"
        onClick={() => onOpenChange(false)}
        className="absolute inset-0 z-0 bg-background/70 backdrop-blur-sm"
      />
      <div
        className={cn(
          "relative z-10 w-[92vw] max-w-md overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-2xl",
        )}
      >
        <div className="flex items-baseline justify-between border-b px-4 py-3">
          <h2 className="text-sm font-semibold">Display settings</h2>
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            esc to close
          </span>
        </div>
        <div className="px-4 py-4">
          <SettingToggle
            label="Full-width content"
            description="Stretch diffs, thread descriptions and steps to the full viewport width."
            checked={fullWidth}
            onChange={setFullWidth}
          />
        </div>
      </div>
    </div>
  );
}

function SettingToggle({
  label,
  description,
  checked,
  onChange,
}: {
  label: string;
  description: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}) {
  return (
    <label className="flex cursor-pointer items-start justify-between gap-4">
      <span className="min-w-0">
        <span className="block text-sm font-medium">{label}</span>
        <span className="mt-0.5 block text-xs text-muted-foreground">
          {description}
        </span>
      </span>
      <span
        className={cn(
          "relative mt-0.5 inline-flex h-5 w-9 shrink-0 cursor-pointer items-center rounded-full transition-colors",
          checked ? "bg-foreground" : "bg-muted",
        )}
      >
        <input
          type="checkbox"
          checked={checked}
          onChange={(e) => onChange(e.target.checked)}
          className="sr-only"
        />
        <span
          className={cn(
            "inline-block size-4 transform rounded-full bg-background shadow transition-transform",
            checked ? "translate-x-[1.125rem]" : "translate-x-0.5",
          )}
        />
      </span>
    </label>
  );
}
