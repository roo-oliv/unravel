"use client";

import { useEffect } from "react";

import {
  type Theme,
  type ThemeId,
  type ThemeMode,
  THEMES,
  getTheme,
  themesForMode,
} from "@/lib/themes";
import { useUiSettings } from "@/lib/ui-settings";
import { cn } from "@/lib/utils";

interface Props {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function ThemePalettePopover({ open, onOpenChange }: Props) {
  const mode = useUiSettings((s) => s.mode);
  const lightTheme = useUiSettings((s) => s.lightTheme);
  const darkTheme = useUiSettings((s) => s.darkTheme);
  const setMode = useUiSettings((s) => s.setMode);
  const setLightTheme = useUiSettings((s) => s.setLightTheme);
  const setDarkTheme = useUiSettings((s) => s.setDarkTheme);

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

  const lightPalette = getTheme(lightTheme);
  const darkPalette = getTheme(darkTheme);
  const lightThemes = themesForMode("light");
  const darkThemes = themesForMode("dark");

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Choose color theme"
      className="fixed inset-0 z-50 flex items-center justify-center"
    >
      <button
        type="button"
        aria-label="Close color theme picker"
        onClick={() => onOpenChange(false)}
        className="absolute inset-0 z-0 bg-background/70 backdrop-blur-sm"
      />
      <div
        className={cn(
          "relative z-10 w-[min(52rem,94vw)] overflow-hidden rounded-xl border bg-popover text-popover-foreground shadow-2xl",
        )}
      >
        <div className="flex items-baseline justify-between border-b px-4 py-3">
          <h2 className="text-sm font-semibold uppercase tracking-wider">
            Choose color theme
          </h2>
          <span className="font-mono text-[10px] uppercase tracking-wider text-muted-foreground">
            esc to close
          </span>
        </div>

        <div className="border-b px-4 py-3">
          <div className="grid grid-cols-3 gap-2">
            <ModeToggleButton
              active={mode === "light"}
              onClick={() => setMode("light")}
              label="Light theme"
              swatches={lightPalette.swatches}
            />
            <ModeToggleButton
              active={mode === "dark"}
              onClick={() => setMode("dark")}
              label="Dark theme"
              swatches={darkPalette.swatches}
            />
            <ModeToggleButton
              active={mode === "system"}
              onClick={() => setMode("system")}
              label="Sync with OS"
              swatches={lightPalette.swatches}
              swatchesSecondary={darkPalette.swatches}
            />
          </div>
        </div>

        <div className="px-4 py-4">
          {mode === "system" ? (
            <SyncDescription
              lightLabel={lightPalette.label}
              darkLabel={darkPalette.label}
            />
          ) : (
            <ThemeGrid
              themes={mode === "light" ? lightThemes : darkThemes}
              selectedId={mode === "light" ? lightTheme : darkTheme}
              onPick={(id) =>
                mode === "light" ? setLightTheme(id) : setDarkTheme(id)
              }
            />
          )}
        </div>
      </div>
    </div>
  );
}

function ModeToggleButton({
  active,
  onClick,
  label,
  swatches,
  swatchesSecondary,
}: {
  active: boolean;
  onClick: () => void;
  label: string;
  swatches: Theme["swatches"];
  swatchesSecondary?: Theme["swatches"];
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={active}
      className={cn(
        "flex flex-col items-start gap-1.5 rounded-lg border px-3 py-2 text-left text-xs transition-colors",
        active
          ? "border-ring ring-2 ring-ring/40"
          : "border-border hover:bg-accent hover:text-accent-foreground",
      )}
    >
      <SwatchRow swatches={swatches} size="sm" />
      {swatchesSecondary && (
        <SwatchRow swatches={swatchesSecondary} size="sm" />
      )}
      <span className="mt-0.5 font-medium">{label}</span>
    </button>
  );
}

function ThemeGrid({
  themes,
  selectedId,
  onPick,
}: {
  themes: Theme[];
  selectedId: ThemeId;
  onPick: (id: ThemeId) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 md:grid-cols-4">
      {themes.map((theme) => {
        const active = theme.id === selectedId;
        return (
          <button
            key={theme.id}
            type="button"
            onClick={() => onPick(theme.id)}
            aria-pressed={active}
            className={cn(
              "flex flex-col items-start gap-1.5 rounded-lg border px-3 py-2 text-left text-xs transition-colors",
              active
                ? "border-ring ring-2 ring-ring/40"
                : "border-border hover:bg-accent hover:text-accent-foreground",
            )}
          >
            <SwatchRow swatches={theme.swatches} size="md" />
            <span className="mt-0.5 font-medium">{theme.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function SwatchRow({
  swatches,
  size,
}: {
  swatches: Theme["swatches"];
  size: "sm" | "md";
}) {
  const sizeClass = size === "sm" ? "size-3" : "size-4";
  return (
    <span className="flex items-center -space-x-1">
      {swatches.map((hsl, i) => (
        <span
          key={i}
          className={cn(
            "inline-block rounded-full border border-border/60",
            sizeClass,
          )}
          style={{ backgroundColor: `hsl(${hsl})` }}
          aria-hidden="true"
        />
      ))}
    </span>
  );
}

function SyncDescription({
  lightLabel,
  darkLabel,
}: {
  lightLabel: string;
  darkLabel: string;
}) {
  return (
    <div className="rounded-md border border-dashed border-border bg-muted/30 px-3 py-3 text-xs text-muted-foreground">
      Following your OS preference.{" "}
      <span className="text-foreground">
        Light: <span className="font-medium">{lightLabel}</span>
      </span>
      {" · "}
      <span className="text-foreground">
        Dark: <span className="font-medium">{darkLabel}</span>
      </span>
      .
      <div className="mt-1 text-[11px] opacity-80">
        Switch to{" "}
        <span className="font-medium text-foreground">Light theme</span> or{" "}
        <span className="font-medium text-foreground">Dark theme</span> above to
        change either assignment.
      </div>
    </div>
  );
}

// Re-export the THEMES catalog so callers that need to compute previews can
// avoid pulling in the popover module by accident.
export { THEMES };
export type { ThemeMode };
