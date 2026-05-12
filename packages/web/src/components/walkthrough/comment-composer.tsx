"use client";

import {
  Bold,
  Code,
  Code2,
  Heading,
  Italic,
  Link as LinkIcon,
  List,
  ListOrdered,
  Quote,
} from "lucide-react";
import {
  forwardRef,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { cn } from "@/lib/utils";

import { Markdown } from "./markdown";

export interface CommentComposerHandle {
  focus(): void;
  /** Read the current draft body without forcing the parent to mirror state. */
  getValue(): string;
  /** Replace the draft body (used after a successful submit). */
  setValue(value: string): void;
}

interface Props {
  value: string;
  onChange: (next: string) => void;
  placeholder?: string;
  disabled?: boolean;
  rows?: number;
  /** Slot for the action buttons rendered under the editor. */
  actions?: ReactNode;
  /** When provided, ``⌘↵`` (mac) / ``Ctrl+↵`` triggers this. */
  onSubmit?: () => void;
  /** When provided, ``Escape`` triggers this. */
  onCancel?: () => void;
  className?: string;
  autoFocus?: boolean;
  /** Compact variant: smaller padding + font (used in inline diff replies). */
  compact?: boolean;
}

/**
 * GitHub-style Markdown composer: Write / Preview tabs and a small toolbar
 * that wraps the current selection with the matching syntax.
 *
 * Stateless re: the body — the parent owns ``value``. Internal state covers
 * Write/Preview tabs and the toolbar's selection-wrap implementation.
 */
export const CommentComposer = forwardRef<CommentComposerHandle, Props>(
  function CommentComposer(
    {
      value,
      onChange,
      placeholder = "Leave a comment (Markdown supported)…",
      disabled = false,
      rows = 4,
      actions,
      onSubmit,
      onCancel,
      className,
      autoFocus = false,
      compact = false,
    },
    ref,
  ) {
    const textareaRef = useRef<HTMLTextAreaElement>(null);
    const [mode, setMode] = useState<"write" | "preview">("write");

    useImperativeHandle(
      ref,
      () => ({
        focus: () => textareaRef.current?.focus(),
        getValue: () => textareaRef.current?.value ?? "",
        setValue: (v: string) => {
          if (textareaRef.current) textareaRef.current.value = v;
          onChange(v);
        },
      }),
      [onChange],
    );

    const apply = (kind: ToolbarAction) => {
      const ta = textareaRef.current;
      if (!ta) return;
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const next = transform(value, start, end, kind);
      onChange(next.value);
      // Restore selection on the next tick so the user keeps editing the
      // freshly wrapped fragment without losing focus.
      requestAnimationFrame(() => {
        if (!textareaRef.current) return;
        textareaRef.current.focus();
        textareaRef.current.setSelectionRange(
          next.selectionStart,
          next.selectionEnd,
        );
      });
    };

    const handleKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
        if (onSubmit) {
          e.preventDefault();
          onSubmit();
        }
        return;
      }
      if (e.key === "Escape" && onCancel) {
        e.preventDefault();
        onCancel();
        return;
      }
      // Hotkeys for the common toolbar actions.
      if (e.metaKey || e.ctrlKey) {
        const code = e.key.toLowerCase();
        if (code === "b") {
          e.preventDefault();
          apply("bold");
        } else if (code === "i") {
          e.preventDefault();
          apply("italic");
        } else if (code === "k") {
          e.preventDefault();
          apply("link");
        }
      }
    };

    const previewBody = useMemo(() => value.trim() || "_Nothing to preview._", [value]);

    return (
      <div
        className={cn(
          "rounded-md border bg-background",
          disabled && "opacity-60",
          className,
        )}
      >
        <div className="flex items-center justify-between gap-2 border-b px-1.5 py-1">
          <div role="tablist" className="flex items-center gap-0.5">
            <TabButton
              active={mode === "write"}
              onClick={() => setMode("write")}
              compact={compact}
            >
              Write
            </TabButton>
            <TabButton
              active={mode === "preview"}
              onClick={() => setMode("preview")}
              compact={compact}
            >
              Preview
            </TabButton>
          </div>
          {mode === "write" && (
            <div className="flex items-center gap-0.5">
              <ToolbarButton title="Heading" onClick={() => apply("heading")}>
                <Heading className="size-3.5" />
              </ToolbarButton>
              <ToolbarButton title="Bold (⌘B)" onClick={() => apply("bold")}>
                <Bold className="size-3.5" />
              </ToolbarButton>
              <ToolbarButton title="Italic (⌘I)" onClick={() => apply("italic")}>
                <Italic className="size-3.5" />
              </ToolbarButton>
              <ToolbarButton title="Quote" onClick={() => apply("quote")}>
                <Quote className="size-3.5" />
              </ToolbarButton>
              <ToolbarButton title="Inline code" onClick={() => apply("code")}>
                <Code className="size-3.5" />
              </ToolbarButton>
              <ToolbarButton title="Code block" onClick={() => apply("codeblock")}>
                <Code2 className="size-3.5" />
              </ToolbarButton>
              <ToolbarButton title="Link (⌘K)" onClick={() => apply("link")}>
                <LinkIcon className="size-3.5" />
              </ToolbarButton>
              <ToolbarButton title="Bulleted list" onClick={() => apply("ul")}>
                <List className="size-3.5" />
              </ToolbarButton>
              <ToolbarButton
                title="Numbered list"
                onClick={() => apply("ol")}
              >
                <ListOrdered className="size-3.5" />
              </ToolbarButton>
            </div>
          )}
        </div>
        {mode === "write" ? (
          <textarea
            ref={textareaRef}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onKeyDown={handleKey}
            placeholder={placeholder}
            disabled={disabled}
            rows={rows}
            autoFocus={autoFocus}
            className={cn(
              "block w-full resize-y bg-transparent px-3 py-2 focus:outline-none",
              compact ? "text-xs leading-relaxed" : "text-sm leading-relaxed",
            )}
          />
        ) : (
          <div
            className={cn(
              "min-h-[6rem] px-3 py-2",
              compact ? "text-xs" : "text-sm",
            )}
          >
            <Markdown>{previewBody}</Markdown>
          </div>
        )}
        {actions && (
          <div className="flex items-center justify-between gap-2 border-t bg-muted/30 px-2.5 py-1.5">
            <span className="text-[10px] text-muted-foreground">
              ⌘↵ submit · esc cancel · Markdown
            </span>
            <div className="flex items-center gap-2">{actions}</div>
          </div>
        )}
      </div>
    );
  },
);

function TabButton({
  active,
  children,
  onClick,
  compact,
}: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
  compact: boolean;
}) {
  return (
    <button
      type="button"
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={cn(
        "rounded px-2 py-0.5 font-medium transition-colors",
        compact ? "text-[10px]" : "text-xs",
        active
          ? "bg-background text-foreground shadow-sm"
          : "text-muted-foreground hover:bg-accent hover:text-foreground",
      )}
    >
      {children}
    </button>
  );
}

function ToolbarButton({
  title,
  onClick,
  children,
}: {
  title: string;
  onClick: () => void;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      title={title}
      aria-label={title}
      onClick={onClick}
      className="rounded p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
    >
      {children}
    </button>
  );
}

type ToolbarAction =
  | "bold"
  | "italic"
  | "heading"
  | "quote"
  | "code"
  | "codeblock"
  | "link"
  | "ul"
  | "ol";

interface Transformed {
  value: string;
  selectionStart: number;
  selectionEnd: number;
}

/** Apply a Markdown transformation around the current selection. */
function transform(
  current: string,
  start: number,
  end: number,
  action: ToolbarAction,
): Transformed {
  const before = current.slice(0, start);
  const selected = current.slice(start, end);
  const after = current.slice(end);

  const wrapInline = (delim: string, placeholder: string): Transformed => {
    const inner = selected || placeholder;
    const next = `${before}${delim}${inner}${delim}${after}`;
    const innerStart = before.length + delim.length;
    return {
      value: next,
      selectionStart: innerStart,
      selectionEnd: innerStart + inner.length,
    };
  };

  const prefixLines = (prefix: string, placeholder: string): Transformed => {
    const inner = selected || placeholder;
    const prefixed = inner
      .split("\n")
      .map((line) => `${prefix}${line}`)
      .join("\n");
    const next = `${before}${prefixed}${after}`;
    return {
      value: next,
      selectionStart: before.length,
      selectionEnd: before.length + prefixed.length,
    };
  };

  switch (action) {
    case "bold":
      return wrapInline("**", "bold text");
    case "italic":
      return wrapInline("_", "italic");
    case "code":
      return wrapInline("`", "code");
    case "heading":
      return prefixLines("### ", "Heading");
    case "quote":
      return prefixLines("> ", "Quote");
    case "ul":
      return prefixLines("- ", "Item");
    case "ol": {
      const inner = selected || "Item";
      const lines = inner.split("\n");
      const prefixed = lines
        .map((line, i) => `${i + 1}. ${line}`)
        .join("\n");
      const next = `${before}${prefixed}${after}`;
      return {
        value: next,
        selectionStart: before.length,
        selectionEnd: before.length + prefixed.length,
      };
    }
    case "codeblock": {
      const inner = selected || "code";
      const block = `\`\`\`\n${inner}\n\`\`\``;
      const next = `${before}${block}${after}`;
      const innerStart = before.length + 4; // ``` + newline
      return {
        value: next,
        selectionStart: innerStart,
        selectionEnd: innerStart + inner.length,
      };
    }
    case "link": {
      const label = selected || "link text";
      const text = `[${label}](https://)`;
      const next = `${before}${text}${after}`;
      const urlStart = before.length + label.length + 3; // [label](
      return {
        value: next,
        selectionStart: urlStart,
        selectionEnd: urlStart + "https://".length,
      };
    }
  }
}
