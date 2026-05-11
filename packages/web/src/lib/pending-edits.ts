"use client";

import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

import type { EditPayload, EditTargetKind } from "@/lib/api";

export interface PendingEdit {
  targetKind: EditTargetKind;
  targetUuid: string;
  field: string;
  originalValue: string;
  value: string;
  stagedAt: string; // ISO timestamp
}

export function makeEditKey(
  targetKind: EditTargetKind,
  targetUuid: string,
  field: string,
): string {
  return `${targetKind}:${targetUuid}:${field}`;
}

interface PendingEditsState {
  // walkthroughUuid → editKey → PendingEdit
  edits: Record<string, Record<string, PendingEdit>>;
  stage(walkthroughUuid: string, edit: PendingEdit): void;
  unstage(walkthroughUuid: string, key: string): void;
  clearWalkthrough(walkthroughUuid: string): void;
}

/**
 * Single source of truth for unsaved edits. Persisted to localStorage so a
 * refresh keeps the user's pending work. Stale entries (where original ===
 * value) are silently dropped on stage.
 */
export const usePendingEditsStore = create<PendingEditsState>()(
  persist(
    (set) => ({
      edits: {},
      stage: (walkthroughUuid, edit) =>
        set((state) => {
          const key = makeEditKey(edit.targetKind, edit.targetUuid, edit.field);
          const forWalkthrough = { ...(state.edits[walkthroughUuid] ?? {}) };
          if (edit.value === edit.originalValue) {
            // No-op stage — drop any prior pending edit for this field.
            delete forWalkthrough[key];
          } else {
            forWalkthrough[key] = edit;
          }
          const nextEdits = { ...state.edits, [walkthroughUuid]: forWalkthrough };
          if (Object.keys(forWalkthrough).length === 0) {
            delete nextEdits[walkthroughUuid];
          }
          return { edits: nextEdits };
        }),
      unstage: (walkthroughUuid, key) =>
        set((state) => {
          const forWalkthrough = { ...(state.edits[walkthroughUuid] ?? {}) };
          if (!(key in forWalkthrough)) return state;
          delete forWalkthrough[key];
          const nextEdits = { ...state.edits, [walkthroughUuid]: forWalkthrough };
          if (Object.keys(forWalkthrough).length === 0) {
            delete nextEdits[walkthroughUuid];
          }
          return { edits: nextEdits };
        }),
      clearWalkthrough: (walkthroughUuid) =>
        set((state) => {
          if (!(walkthroughUuid in state.edits)) return state;
          const nextEdits = { ...state.edits };
          delete nextEdits[walkthroughUuid];
          return { edits: nextEdits };
        }),
    }),
    {
      name: "unravel:pending-edits:v1",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);

export function toEditPayloads(
  edits: Record<string, PendingEdit>,
): EditPayload[] {
  return Object.values(edits).map((e) => ({
    target_kind: e.targetKind,
    target_id: e.targetUuid,
    field: e.field,
    value: e.value,
  }));
}
