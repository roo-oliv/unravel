import {
  DEFAULT_DARK,
  DEFAULT_LIGHT,
  DEFAULT_MODE,
  THEME_IDS,
} from "@/lib/themes";
import { UI_SETTINGS_STORAGE_KEY } from "@/lib/ui-settings";

/**
 * Inline script injected into <head> to apply the persisted theme before
 * hydration, preventing a flash of the wrong colors.
 *
 * Tolerates missing/corrupted localStorage by falling back to defaults.
 * Reads the same Zustand persist payload that ui-settings.ts writes.
 */
function buildScript() {
  const validIds = JSON.stringify(THEME_IDS);
  return `
(function () {
  try {
    var KEY = ${JSON.stringify(UI_SETTINGS_STORAGE_KEY)};
    var VALID = ${validIds};
    var mode = ${JSON.stringify(DEFAULT_MODE)};
    var light = ${JSON.stringify(DEFAULT_LIGHT)};
    var dark = ${JSON.stringify(DEFAULT_DARK)};
    var raw = localStorage.getItem(KEY);
    if (raw) {
      var parsed = JSON.parse(raw);
      var s = parsed && parsed.state ? parsed.state : null;
      if (s) {
        if (s.mode === "light" || s.mode === "dark" || s.mode === "system") mode = s.mode;
        if (VALID.indexOf(s.lightTheme) !== -1) light = s.lightTheme;
        if (VALID.indexOf(s.darkTheme) !== -1) dark = s.darkTheme;
      }
    }
    var prefersDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
    var isDark = mode === "dark" || (mode === "system" && prefersDark);
    var themeId = isDark ? dark : light;
    var root = document.documentElement;
    root.setAttribute("data-theme", themeId);
    root.classList.toggle("dark", isDark);
    root.style.colorScheme = isDark ? "dark" : "light";
  } catch (e) {
    // Swallow — defaults already render via :root in globals.css.
  }
})();
`.trim();
}

export function ThemeScript() {
  return (
    <script
      // eslint-disable-next-line react/no-danger
      dangerouslySetInnerHTML={{ __html: buildScript() }}
    />
  );
}
