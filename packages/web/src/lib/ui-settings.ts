"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import {
  DEFAULT_DARK,
  DEFAULT_LIGHT,
  DEFAULT_MODE,
  type ThemeId,
  type ThemeMode,
} from "./themes";

interface UiSettingsState {
  /** When true, content containers (overview, thread title, steps, diffs) stretch
   * to fill the available viewport width instead of being capped at max-w-4xl.
   * GitHub-PR-style by default — large diffs are easier to read with the
   * extra horizontal room. */
  fullWidth: boolean;
  setFullWidth(value: boolean): void;
  toggleFullWidth(): void;

  /** Color theme picker. `mode` decides whether the user-selected
   * lightTheme, darkTheme, or the OS-preferred one is applied. */
  mode: ThemeMode;
  lightTheme: ThemeId;
  darkTheme: ThemeId;
  setMode(value: ThemeMode): void;
  setLightTheme(id: ThemeId): void;
  setDarkTheme(id: ThemeId): void;
}

export const UI_SETTINGS_STORAGE_KEY = "unravel:ui-settings:v2";

export const useUiSettings = create<UiSettingsState>()(
  persist(
    (set) => ({
      fullWidth: true,
      setFullWidth: (value) => set({ fullWidth: value }),
      toggleFullWidth: () => set((s) => ({ fullWidth: !s.fullWidth })),

      mode: DEFAULT_MODE,
      lightTheme: DEFAULT_LIGHT,
      darkTheme: DEFAULT_DARK,
      setMode: (value) => set({ mode: value }),
      setLightTheme: (id) => set({ lightTheme: id }),
      setDarkTheme: (id) => set({ darkTheme: id }),
    }),
    {
      name: UI_SETTINGS_STORAGE_KEY,
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
