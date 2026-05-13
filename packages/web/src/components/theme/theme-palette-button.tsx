"use client";

import { Palette } from "lucide-react";
import { useState } from "react";

import { ThemePalettePopover } from "./theme-palette-popover";

interface Props {
  /** Render a keyboard hint ("t") to the left of the icon. */
  showHotkey?: boolean;
  /** Optional className override for the trigger button. */
  className?: string;
}

/**
 * Header trigger + popover for the color theme picker. Manages its own
 * open state. Consumers can pass `showHotkey` to display the `t` hint
 * (matching the TUI keybinding) when the surrounding header also wires up
 * the global hotkey.
 */
export function ThemePaletteButton({
  showHotkey = false,
  className,
}: Props = {}) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label="Choose color theme"
        title="Choose color theme"
        className={
          className ??
          "flex items-center gap-1.5 rounded px-1.5 py-0.5 hover:bg-accent hover:text-foreground"
        }
      >
        {showHotkey && (
          <kbd className="rounded border bg-background px-1 font-mono text-[10px]">
            t
          </kbd>
        )}
        <Palette className="size-3.5" aria-hidden="true" />
      </button>
      <ThemePalettePopover open={open} onOpenChange={setOpen} />
    </>
  );
}
