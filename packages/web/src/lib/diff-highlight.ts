import type { BundledLanguage, Highlighter, ThemedToken } from "shiki";

const LANG_BY_EXT: Record<string, BundledLanguage> = {
  ts: "typescript",
  tsx: "tsx",
  mts: "typescript",
  cts: "typescript",
  js: "javascript",
  jsx: "jsx",
  mjs: "javascript",
  cjs: "javascript",
  py: "python",
  rb: "ruby",
  go: "go",
  rs: "rust",
  java: "java",
  kt: "kotlin",
  swift: "swift",
  c: "c",
  h: "c",
  cpp: "cpp",
  cc: "cpp",
  hpp: "cpp",
  cs: "csharp",
  php: "php",
  json: "json",
  jsonc: "jsonc",
  yaml: "yaml",
  yml: "yaml",
  toml: "toml",
  md: "markdown",
  mdx: "mdx",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  fish: "fish",
  css: "css",
  scss: "scss",
  less: "less",
  html: "html",
  vue: "vue",
  svelte: "svelte",
  xml: "xml",
  sql: "sql",
};

const PRELOADED_LANGS: BundledLanguage[] = [
  "typescript",
  "tsx",
  "javascript",
  "jsx",
  "python",
  "go",
  "rust",
  "json",
  "yaml",
  "markdown",
  "bash",
  "css",
  "html",
  "sql",
];

export const LIGHT_THEME = "github-light";
export const DARK_THEME = "github-dark";

export function languageForPath(path: string): BundledLanguage | "text" {
  const base = path.split("/").pop()?.toLowerCase() ?? "";
  if (base === "dockerfile" || base.endsWith(".dockerfile")) return "text";
  const ext = base.includes(".") ? base.split(".").pop()! : "";
  return LANG_BY_EXT[ext] ?? "text";
}

let highlighterPromise: Promise<Highlighter> | null = null;

export function getDiffHighlighter(): Promise<Highlighter> {
  if (!highlighterPromise) {
    highlighterPromise = import("shiki").then(({ createHighlighter }) =>
      createHighlighter({
        themes: [LIGHT_THEME, DARK_THEME],
        langs: PRELOADED_LANGS,
      }),
    );
  }
  return highlighterPromise;
}

export type LineKind = "add" | "del" | "ctx" | "hunk";

export interface DiffLine {
  kind: LineKind;
  raw: string;
  prefix: string;
  tokens: ThemedToken[];
}

interface ClassifiedLine {
  kind: LineKind;
  prefix: string;
  body: string;
  raw: string;
}

function classifyLine(line: string): ClassifiedLine {
  if (line.startsWith("@@")) {
    return { kind: "hunk", prefix: "", body: line, raw: line };
  }
  if (line.startsWith("+") && !line.startsWith("+++")) {
    return { kind: "add", prefix: "+", body: line.slice(1), raw: line };
  }
  if (line.startsWith("-") && !line.startsWith("---")) {
    return { kind: "del", prefix: "-", body: line.slice(1), raw: line };
  }
  if (line.startsWith(" ")) {
    return { kind: "ctx", prefix: " ", body: line.slice(1), raw: line };
  }
  return { kind: "ctx", prefix: "", body: line, raw: line };
}

export function classifyDiff(content: string): ClassifiedLine[] {
  return content.split("\n").map(classifyLine);
}

export async function highlightDiff(
  content: string,
  filePath: string,
): Promise<DiffLine[]> {
  const classified = classifyDiff(content);
  const lang = languageForPath(filePath);

  if (lang === "text") {
    return classified.map((c) => ({
      kind: c.kind,
      raw: c.raw,
      prefix: c.prefix,
      tokens: [{ content: c.body, offset: 0 }],
    }));
  }

  const highlighter = await getDiffHighlighter();
  if (!highlighter.getLoadedLanguages().includes(lang)) {
    try {
      await highlighter.loadLanguage(lang);
    } catch {
      return classified.map((c) => ({
        kind: c.kind,
        raw: c.raw,
        prefix: c.prefix,
        tokens: [{ content: c.body, offset: 0 }],
      }));
    }
  }
  const code = classified.map((c) => c.body).join("\n");
  const result = highlighter.codeToTokens(code, {
    lang,
    themes: { light: LIGHT_THEME, dark: DARK_THEME },
    defaultColor: false,
  });

  return classified.map((c, i) => ({
    kind: c.kind,
    raw: c.raw,
    prefix: c.prefix,
    tokens: result.tokens[i] ?? [{ content: c.body, offset: 0 }],
  }));
}
