"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

interface UiSettingsState {
  /** When true, content containers (overview, thread title, steps, diffs) stretch
   * to fill the available viewport width instead of being capped at max-w-4xl.
   * GitHub-PR-style by default — large diffs are easier to read with the
   * extra horizontal room. */
  fullWidth: boolean;
  setFullWidth(value: boolean): void;
  toggleFullWidth(): void;
}

export const useUiSettings = create<UiSettingsState>()(
  persist(
    (set) => ({
      fullWidth: true,
      setFullWidth: (value) => set({ fullWidth: value }),
      toggleFullWidth: () => set((s) => ({ fullWidth: !s.fullWidth })),
    }),
    {
      name: "unravel:ui-settings:v1",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
