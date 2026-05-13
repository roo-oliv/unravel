"use client";

import { useEffect } from "react";

import { resolveActiveTheme } from "@/lib/themes";
import { useUiSettings } from "@/lib/ui-settings";

/**
 * Mounted once inside Providers. Applies theme changes from the Zustand
 * store to <html>, and re-resolves the active theme when the OS preference
 * flips (only matters when mode === "system").
 */
export function ThemeSync() {
  const mode = useUiSettings((s) => s.mode);
  const lightTheme = useUiSettings((s) => s.lightTheme);
  const darkTheme = useUiSettings((s) => s.darkTheme);

  useEffect(() => {
    const mql = window.matchMedia("(prefers-color-scheme: dark)");

    const apply = () => {
      const { themeId, isDark } = resolveActiveTheme(
        mode,
        lightTheme,
        darkTheme,
        mql.matches,
      );
      const root = document.documentElement;
      root.setAttribute("data-theme", themeId);
      root.classList.toggle("dark", isDark);
      root.style.colorScheme = isDark ? "dark" : "light";
    };

    apply();

    if (mode !== "system") return;
    // Modern browsers expose addEventListener; Safari < 14 used addListener.
    if (typeof mql.addEventListener === "function") {
      mql.addEventListener("change", apply);
      return () => mql.removeEventListener("change", apply);
    }
    mql.addListener(apply);
    return () => mql.removeListener(apply);
  }, [mode, lightTheme, darkTheme]);

  return null;
}
