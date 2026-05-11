"use client";

import { Check, Pencil, X } from "lucide-react";
import { useEffect, useLayoutEffect, useRef, useState } from "react";

import type { EditTargetKind, FieldEditDTO } from "@/lib/api";
import {
  makeEditKey,
  usePendingEditsStore,
  type PendingEdit,
} from "@/lib/pending-edits";
import { cn } from "@/lib/utils";

import { EditHistoryPopover } from "./edit-history-popover";
import { Markdown } from "./markdown";

interface Props {
  walkthroughUuid: string;
  targetKind: EditTargetKind;
  targetUuid: string;
  field: string;
  originalValue: string;
  /** History rows filtered to this exact (target, field). */
  history: FieldEditDTO[];
  /** Tailwind classes applied to the display markdown wrapper + textarea. */
  textClassName?: string;
  /** Outer container classes (e.g. flex layout overrides). */
  className?: string;
  /** Placeholder shown when value is empty in both display and edit modes. */
  placeholder?: string;
  /** Whether to render content as Markdown when not editing (default true). */
  asMarkdown?: boolean;
  /** Single-line input mode (no wrap, Enter saves) — used for titles. */
  singleLine?: boolean;
  /** Min height for the textarea in pixels (autosize grows from here). */
  minRows?: number;
}

/**
 * Generic editable field with a 3-state UX:
 *
 *  - Pristine: display value, pencil appears on hover. Text itself is not
 *    clickable — keeps selection/copy ergonomics intact. Only the pencil
 *    enters edit mode.
 *  - Pending (staged in local cache): display the staged value, amber pencil
 *    always visible. Clicking the pencil enters edit mode with the staged
 *    value as the starting draft.
 *  - Editing: textarea/input with ✓ (stage) and ✗ (discard draft) controls in
 *    the top-right. Clicking outside the field stages the draft (forgiving
 *    against accidental misclicks); Escape or ✗ discards it explicitly.
 *
 * The pending edit goes into a Zustand store persisted to localStorage. The
 * server is only contacted on global Submit (handled by ``PendingEditsBar``).
 */
export function EditableField({
  walkthroughUuid,
  targetKind,
  targetUuid,
  field,
  originalValue,
  history,
  textClassName,
  className,
  placeholder,
  asMarkdown = true,
  singleLine = false,
  minRows = 1,
}: Props) {
  const editKey = makeEditKey(targetKind, targetUuid, field);
  const pending = usePendingEditsStore(
    (s) => s.edits[walkthroughUuid]?.[editKey],
  );
  const stage = usePendingEditsStore((s) => s.stage);
  const unstage = usePendingEditsStore((s) => s.unstage);

  const displayValue = pending?.value ?? originalValue;
  const isDirty = !!pending;

  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(displayValue);
  const containerRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // Whenever the source value changes (server save, walkthrough refetch) reset
  // the draft baseline. We don't sync mid-edit; once user is in edit mode the
  // textarea owns the draft until they exit.
  useEffect(() => {
    if (!editing) setDraft(displayValue);
  }, [displayValue, editing]);

  // Autosize textarea to fit content.
  useLayoutEffect(() => {
    const el = textareaRef.current;
    if (!el || !editing) return;
    el.style.height = "auto";
    el.style.height = `${el.scrollHeight}px`;
  }, [draft, editing]);

  // Click-outside stages the draft (forgiving misclicks); Escape discards it.
  // We use a ref to read the latest draft inside the listeners without
  // re-binding the document handlers on every keystroke.
  const draftRef = useRef(draft);
  useEffect(() => {
    draftRef.current = draft;
  }, [draft]);

  useEffect(() => {
    if (!editing) return;
    const onMouseDown = (e: MouseEvent) => {
      if (
        containerRef.current &&
        !containerRef.current.contains(e.target as Node)
      ) {
        // Mirror handleSave: stage on click-outside.
        const liveDraft = draftRef.current;
        if (liveDraft === originalValue) {
          unstage(walkthroughUuid, editKey);
        } else if (!pending || liveDraft !== pending.value) {
          stage(walkthroughUuid, {
            targetKind,
            targetUuid,
            field,
            originalValue,
            value: liveDraft,
            stagedAt: new Date().toISOString(),
          });
        }
        setEditing(false);
      }
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        setEditing(false);
      }
    };
    document.addEventListener("mousedown", onMouseDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onMouseDown);
      document.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [editing, originalValue, pending, walkthroughUuid, editKey, field]);

  const handleEnter = () => {
    setDraft(displayValue);
    setEditing(true);
  };

  const handleSave = () => {
    if (draft === originalValue) {
      // Draft matches the server value — drop any prior pending entry too.
      unstage(walkthroughUuid, editKey);
    } else if (!pending || draft !== pending.value) {
      // Only stage when the draft actually differs from what's already staged
      // (otherwise we'd churn the store with identical values on every blur).
      const next: PendingEdit = {
        targetKind,
        targetUuid,
        field,
        originalValue,
        value: draft,
        stagedAt: new Date().toISOString(),
      };
      stage(walkthroughUuid, next);
    }
    setEditing(false);
  };

  const handleDiscardDraft = () => {
    setEditing(false);
  };

  // Discard the staged (but not yet submitted) edit and restore original.
  const handleClearPending = () => {
    unstage(walkthroughUuid, editKey);
    setDraft(originalValue);
  };

  const showControls = editing;
  const showPencil = !editing;

  return (
    <div
      ref={containerRef}
      className={cn(
        "group/field relative -mx-1 rounded px-1",
        isDirty &&
          !editing &&
          "bg-amber-50/40 ring-1 ring-amber-200/60 dark:bg-amber-950/20 dark:ring-amber-900/40",
        className,
      )}
    >
      {!editing ? (
        // Plain text container — not clickable, so user can select and copy
        // without accidentally entering edit mode. The pencil button is the
        // only affordance for editing.
        <div className="block w-full rounded px-0 py-0.5 text-left">
          {displayValue ? (
            asMarkdown ? (
              <Markdown className={textClassName}>{displayValue}</Markdown>
            ) : (
              <span className={cn("block", textClassName)}>{displayValue}</span>
            )
          ) : (
            <span
              className={cn("italic text-muted-foreground/70", textClassName)}
            >
              {placeholder ?? "(empty — click pencil to edit)"}
            </span>
          )}
        </div>
      ) : singleLine ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              handleSave();
            }
          }}
          spellCheck={false}
          className={cn(
            "w-full bg-muted/30 px-1 py-0.5",
            "font-sans text-foreground",
            "rounded outline-none focus:ring-2 focus:ring-ring",
            textClassName,
          )}
        />
      ) : (
        <textarea
          ref={textareaRef}
          autoFocus
          value={draft}
          rows={minRows}
          spellCheck={false}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
              e.preventDefault();
              handleSave();
            }
          }}
          className={cn(
            "w-full resize-none bg-muted/30 px-1 py-0.5",
            "font-sans text-foreground",
            "rounded outline-none focus:ring-2 focus:ring-ring",
            "min-h-[2rem]",
            textClassName,
          )}
        />
      )}

      <div
        className={cn(
          "absolute right-1 top-1 flex items-center gap-0.5",
          // Chip background so the icons don't blur into the text underneath.
          "rounded border bg-background p-0.5 shadow-sm",
          // Pristine pencil: hover-only. Dirty pencil: always visible.
          !isDirty && !editing && "opacity-0 group-hover/field:opacity-100",
        )}
      >
        {showPencil && (
          <>
            <EditHistoryPopover
              history={history}
              highlight={isDirty}
              // Hide on the pristine state until hover; visible always when dirty.
              className={cn(
                !isDirty &&
                  "opacity-0 transition-opacity group-hover/field:opacity-100",
              )}
            />
            {isDirty && (
              <button
                type="button"
                onClick={handleClearPending}
                aria-label="Discard pending edit"
                title="Discard pending edit (restore saved value)"
                className="rounded p-0.5 text-amber-500 hover:bg-accent hover:text-amber-600"
              >
                <X className="size-3" aria-hidden="true" />
              </button>
            )}
            <button
              type="button"
              onClick={handleEnter}
              aria-label={`Edit ${field}`}
              title={isDirty ? "Edit (pending unsaved change)" : "Edit"}
              className={cn(
                "rounded p-0.5 transition-colors",
                "hover:bg-accent",
                isDirty
                  ? "text-amber-500 hover:text-amber-600"
                  : "text-muted-foreground hover:text-foreground",
              )}
            >
              <Pencil className="size-3" aria-hidden="true" />
            </button>
          </>
        )}
        {showControls && (
          <>
            <button
              type="button"
              onMouseDown={(e) => {
                // mousedown (not onClick) so we fire before the document
                // click-outside listener tears down the editor.
                e.preventDefault();
                handleSave();
              }}
              aria-label="Stage edit"
              title="Stage edit (Cmd/Ctrl+Enter)"
              className="rounded p-0.5 text-emerald-600 hover:bg-accent hover:text-emerald-700"
            >
              <Check className="size-3.5" aria-hidden="true" />
            </button>
            <button
              type="button"
              onMouseDown={(e) => {
                e.preventDefault();
                handleDiscardDraft();
              }}
              aria-label="Discard draft"
              title="Discard draft (Esc)"
              className="rounded p-0.5 text-muted-foreground hover:bg-accent hover:text-foreground"
            >
              <X className="size-3.5" aria-hidden="true" />
            </button>
          </>
        )}
      </div>
    </div>
  );
}
