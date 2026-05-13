/**
 * Color theme catalog for the Web UI.
 *
 * Theme ids mirror the Pygments themes the TUI cycles through
 * (see src/unravel/tui/screens/settings.py::_THEME_CYCLE). The TUI uses
 * these names for syntax highlighting only; the Web UI extends each into
 * a full UI palette by populating every CSS variable in globals.css.
 *
 * github-light is added to give the Light bucket two options. If/when the
 * TUI adopts it in _THEME_CYCLE we keep full parity.
 *
 * The CSS variable definitions actually live in globals.css under
 * :root[data-theme="<id>"] blocks. The `tokens` map here documents the
 * canonical values; consumers (theme-script, theme-sync) only need
 * `id`, `label`, `mode`, and `swatches`.
 */
export type ThemeMode = "light" | "dark" | "system";

export const THEME_IDS = [
  "github-light",
  "solarized-light",
  "monokai",
  "dracula",
  "github-dark",
  "solarized-dark",
  "one-dark",
  "native",
] as const;
export type ThemeId = (typeof THEME_IDS)[number];

export interface Theme {
  id: ThemeId;
  label: string;
  mode: "light" | "dark";
  /** Five representative HSL values shown as preview circles in the picker. */
  swatches: [string, string, string, string, string];
}

export const THEMES: Record<ThemeId, Theme> = {
  "github-light": {
    id: "github-light",
    label: "GitHub Light",
    mode: "light",
    swatches: [
      "0 0% 100%",
      "213 13% 16%",
      "213 80% 47%",
      "134 61% 41%",
      "356 75% 53%",
    ],
  },
  "solarized-light": {
    id: "solarized-light",
    label: "Solarized Light",
    mode: "light",
    swatches: [
      "44 87% 94%",
      "194 14% 40%",
      "175 74% 37%",
      "68 100% 30%",
      "1 71% 52%",
    ],
  },
  monokai: {
    id: "monokai",
    label: "Monokai",
    mode: "dark",
    swatches: [
      "70 8% 15%",
      "60 30% 96%",
      "80 76% 53%",
      "80 76% 53%",
      "338 95% 56%",
    ],
  },
  dracula: {
    id: "dracula",
    label: "Dracula",
    mode: "dark",
    swatches: [
      "231 15% 18%",
      "60 30% 96%",
      "326 100% 74%",
      "135 94% 65%",
      "0 100% 67%",
    ],
  },
  "github-dark": {
    id: "github-dark",
    label: "GitHub Dark",
    mode: "dark",
    swatches: [
      "220 24% 7%",
      "213 27% 84%",
      "212 92% 64%",
      "137 55% 46%",
      "0 64% 56%",
    ],
  },
  "solarized-dark": {
    id: "solarized-dark",
    label: "Solarized Dark",
    mode: "dark",
    swatches: [
      "192 100% 11%",
      "186 8% 55%",
      "175 74% 37%",
      "68 100% 30%",
      "1 71% 52%",
    ],
  },
  "one-dark": {
    id: "one-dark",
    label: "One Dark",
    mode: "dark",
    swatches: [
      "220 13% 18%",
      "219 14% 71%",
      "207 82% 66%",
      "95 38% 62%",
      "355 65% 65%",
    ],
  },
  native: {
    id: "native",
    label: "Native",
    mode: "dark",
    swatches: [
      "0 0% 13%",
      "0 0% 83%",
      "30 100% 50%",
      "120 60% 50%",
      "0 78% 55%",
    ],
  },
};

export const DEFAULT_LIGHT: ThemeId = "github-light";
export const DEFAULT_DARK: ThemeId = "dracula";
export const DEFAULT_MODE: ThemeMode = "dark";

export function themesForMode(mode: "light" | "dark"): Theme[] {
  return THEME_IDS.map((id) => THEMES[id]).filter((t) => t.mode === mode);
}

export function getTheme(id: ThemeId): Theme {
  return THEMES[id];
}

export function isThemeId(value: unknown): value is ThemeId {
  return (
    typeof value === "string" && (THEME_IDS as readonly string[]).includes(value)
  );
}

export function isThemeMode(value: unknown): value is ThemeMode {
  return value === "light" || value === "dark" || value === "system";
}

/**
 * Resolve which theme is active given a mode + the two user-selected ids
 * and whether the OS reports a dark preference. Used by ThemeScript and
 * ThemeSync to keep them in lockstep.
 */
export function resolveActiveTheme(
  mode: ThemeMode,
  lightId: ThemeId,
  darkId: ThemeId,
  prefersDark: boolean,
): { themeId: ThemeId; isDark: boolean } {
  if (mode === "light") return { themeId: lightId, isDark: false };
  if (mode === "dark") return { themeId: darkId, isDark: true };
  return prefersDark
    ? { themeId: darkId, isDark: true }
    : { themeId: lightId, isDark: false };
}
