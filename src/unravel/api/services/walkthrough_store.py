"""Walkthrough persistence: fixture → DB upsert, DB → DTO hydration.

Phase 0 contract: the first GET for a fixture slug inserts the walkthrough
into Postgres; subsequent GETs serve the DB-backed version (with any narration
edits applied). Re-importing a changed fixture file is out of scope here —
delete the row and reload if you need a fresh import.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from unravel.api.db_models import (
    FieldEdit,
    Hunk,
    Thread,
    ThreadStep,
    ThreadStepHunk,
    Walkthrough,
)

WALKTHROUGH_EDITABLE_FIELDS = {"overview"}
THREAD_EDITABLE_FIELDS = {"title", "summary", "root_cause"}
STEP_EDITABLE_FIELDS = {"narration"}


@dataclass(frozen=True)
class EditRequest:
    target_kind: str  # "thread" | "step"
    target_id: UUID
    field: str
    value: str


class EditValidationError(ValueError):
    """Raised when an edit request fails validation (whitelist or scope)."""


async def get_or_create_walkthrough_from_fixture(
    session: AsyncSession, slug: str, fixture: dict
) -> Walkthrough:
    """Return the persisted Walkthrough for ``slug``, inserting from fixture on first hit.

    If a row already exists, opportunistically backfill PR source columns from
    ``metadata.source`` when present in the fixture and absent on the row.
    This avoids forcing developers to drop walkthroughs after schema additions.
    """
    existing = await load_full_walkthrough(session, slug=slug)
    if existing is not None:
        if _backfill_pr_source(existing, fixture):
            await session.commit()
            # Reload to ensure relationships are still hydrated post-commit.
            existing = await load_full_walkthrough(session, slug=slug)
            assert existing is not None
        return existing

    walkthrough = _build_walkthrough_from_fixture(slug, fixture)
    session.add(walkthrough)
    await session.commit()

    persisted = await load_full_walkthrough(session, slug=slug)
    assert persisted is not None
    return persisted


def _backfill_pr_source(walkthrough: Walkthrough, fixture: dict) -> bool:
    """Populate PR columns from ``metadata.source`` if the row is missing them.

    Returns True if any field was updated (caller should commit).
    """
    if walkthrough.repo_full_name and walkthrough.pr_number:
        return False
    source = (fixture.get("metadata") or {}).get("source") or {}
    if not isinstance(source, dict) or source.get("kind") != "pr":
        return False
    repo = source.get("repo")
    number = source.get("number")
    if not (isinstance(repo, str) and isinstance(number, int)):
        return False
    walkthrough.repo_full_name = repo
    walkthrough.pr_number = number
    walkthrough.pr_head_sha = source.get("head_sha")
    walkthrough.pr_html_url = (
        source.get("html_url") or f"https://github.com/{repo}/pull/{number}"
    )
    walkthrough.pr_title = source.get("title")
    return True


async def load_full_walkthrough(
    session: AsyncSession, *, slug: str | None = None, id: UUID | None = None
) -> Walkthrough | None:
    stmt = select(Walkthrough).options(
        selectinload(Walkthrough.hunks),
        selectinload(Walkthrough.threads).selectinload(Thread.steps).selectinload(
            ThreadStep.hunk_links
        ),
    )
    if slug is not None:
        stmt = stmt.where(Walkthrough.slug == slug)
    elif id is not None:
        stmt = stmt.where(Walkthrough.id == id)
    else:
        raise ValueError("slug or id required")
    result = await session.execute(stmt)
    return result.scalars().first()


def _build_walkthrough_from_fixture(slug: str, fixture: dict) -> Walkthrough:
    """Construct a fully-linked Walkthrough graph from a fixture dict.

    Fixtures may embed full Hunk objects on steps (newer schema) or just refs.
    We collect every unique hunk by ref before linking steps so the (hunk, step)
    join survives either shape.
    """
    raw_threads = fixture.get("threads", [])
    raw_captions: dict[str, str] = fixture.get("hunk_captions", {}) or {}

    hunks_by_ref: dict[str, Hunk] = {}
    for thread in raw_threads:
        for step in thread.get("steps", []):
            for hunk_ref in step.get("hunks", []):
                if isinstance(hunk_ref, dict):
                    ref = hunk_ref.get("id")
                    if not ref or ref in hunks_by_ref:
                        continue
                    hunks_by_ref[ref] = Hunk(
                        ref=ref,
                        file_path=hunk_ref.get("file_path", "") or "",
                        old_start=int(hunk_ref.get("old_start") or 0),
                        old_count=int(hunk_ref.get("old_count") or 0),
                        new_start=int(hunk_ref.get("new_start") or 0),
                        new_count=int(hunk_ref.get("new_count") or 0),
                        content=hunk_ref.get("content") or "",
                        context_before=hunk_ref.get("context_before") or "",
                        context_after=hunk_ref.get("context_after") or "",
                        language=hunk_ref.get("language"),
                        caption=hunk_ref.get("caption")
                        or raw_captions.get(ref, "")
                        or "",
                        additions=int(hunk_ref.get("additions") or 0),
                        deletions=int(hunk_ref.get("deletions") or 0),
                    )
                else:
                    ref = hunk_ref
                    if ref in hunks_by_ref:
                        continue
                    hunks_by_ref[ref] = Hunk(
                        ref=ref,
                        caption=raw_captions.get(ref, ""),
                    )

    threads: list[Thread] = []
    for position, thread in enumerate(raw_threads):
        steps: list[ThreadStep] = []
        for step in thread.get("steps", []):
            step_hunks_refs = [
                h["id"] if isinstance(h, dict) else h
                for h in step.get("hunks", [])
            ]
            step_obj = ThreadStep(
                step_order=int(step.get("order") or len(steps) + 1),
                narration=step.get("narration") or "",
                hunk_links=[
                    ThreadStepHunk(hunk=hunks_by_ref[ref], position=idx)
                    for idx, ref in enumerate(step_hunks_refs)
                    if ref in hunks_by_ref
                ],
            )
            steps.append(step_obj)

        threads.append(
            Thread(
                ref=thread.get("id") or f"thread-{position + 1}",
                position=position,
                title=thread.get("title") or "",
                summary=thread.get("summary") or "",
                root_cause=thread.get("root_cause") or "",
                dependencies=list(thread.get("dependencies") or []),
                steps=steps,
            )
        )

    extra_metadata = dict(fixture.get("metadata") or {})
    source = extra_metadata.get("source") or {}
    pr_fields: dict[str, Any] = {}
    if isinstance(source, dict) and source.get("kind") == "pr":
        repo = source.get("repo")
        number = source.get("number")
        if isinstance(repo, str) and isinstance(number, int):
            pr_fields = {
                "repo_full_name": repo,
                "pr_number": number,
                "pr_head_sha": source.get("head_sha"),
                "pr_html_url": (
                    source.get("html_url")
                    or f"https://github.com/{repo}/pull/{number}"
                ),
                "pr_title": source.get("title"),
            }

    return Walkthrough(
        slug=slug,
        overview=fixture.get("overview") or "",
        suggested_order=list(fixture.get("suggested_order") or []),
        extra_metadata=extra_metadata,
        hunk_captions=dict(raw_captions),
        raw_diff=fixture.get("raw_diff") or "",
        threads=threads,
        hunks=list(hunks_by_ref.values()),
        **pr_fields,
    )


def walkthrough_to_dto(walkthrough: Walkthrough) -> dict[str, Any]:
    """Serialize a fully-loaded Walkthrough into the DTO consumed by the FE.

    The shape mirrors the on-disk fixture JSON, plus stable UUIDs on
    walkthrough / threads / steps so the FE can PATCH them.
    """
    hunks_by_id = {h.id: h for h in walkthrough.hunks}

    thread_dtos: list[dict[str, Any]] = []
    for thread in walkthrough.threads:
        step_dtos: list[dict[str, Any]] = []
        for step in thread.steps:
            hunk_entries: list[dict[str, Any]] = []
            for link in step.hunk_links:
                hunk = hunks_by_id.get(link.hunk_id)
                if hunk is None:
                    continue
                hunk_entries.append(_hunk_to_dto(hunk))
            step_dtos.append(
                {
                    "id": str(step.id),
                    "order": step.step_order,
                    "narration": step.narration,
                    "narration_edited_at": (
                        step.narration_edited_at.isoformat()
                        if step.narration_edited_at
                        else None
                    ),
                    "hunks": hunk_entries,
                }
            )
        thread_dtos.append(
            {
                # The FE uses ``id`` to match ``suggested_order`` (LLM kebab refs).
                # The DB UUID is exposed as ``uuid`` for future PATCH endpoints.
                "id": thread.ref,
                "uuid": str(thread.id),
                "title": thread.title,
                "summary": thread.summary,
                "root_cause": thread.root_cause,
                "dependencies": list(thread.dependencies or []),
                "steps": step_dtos,
            }
        )

    pr: dict[str, Any] | None = None
    if walkthrough.repo_full_name and walkthrough.pr_number:
        pr = {
            "repo": walkthrough.repo_full_name,
            "number": walkthrough.pr_number,
            "html_url": walkthrough.pr_html_url,
            "title": walkthrough.pr_title,
            "head_sha": walkthrough.pr_head_sha,
        }

    return {
        "id": walkthrough.slug,
        "uuid": str(walkthrough.id),
        "slug": walkthrough.slug,
        "overview": walkthrough.overview,
        "suggested_order": list(walkthrough.suggested_order or []),
        "metadata": dict(walkthrough.extra_metadata or {}),
        "hunk_captions": dict(walkthrough.hunk_captions or {}),
        "threads": thread_dtos,
        "pr": pr,
    }


def _hunk_to_dto(hunk: Hunk) -> dict[str, Any]:
    return {
        "id": hunk.ref,
        "file_path": hunk.file_path,
        "old_start": hunk.old_start,
        "old_count": hunk.old_count,
        "new_start": hunk.new_start,
        "new_count": hunk.new_count,
        "content": hunk.content,
        "context_before": hunk.context_before,
        "context_after": hunk.context_after,
        "language": hunk.language,
        "caption": hunk.caption,
        "additions": hunk.additions,
        "deletions": hunk.deletions,
    }


async def apply_edits_batch(
    session: AsyncSession,
    walkthrough: Walkthrough,
    edits: list[EditRequest],
    editor: str,
) -> list[FieldEdit]:
    """Apply a batch of edits transactionally, returning the history rows created.

    Validation rules: each edit's target must belong to ``walkthrough``; field
    name must be in the per-target whitelist; no-op edits (value unchanged) are
    silently skipped (not recorded).
    """
    if not edits:
        return []

    thread_ids = {t.id for t in walkthrough.threads}
    step_ids = {s.id for t in walkthrough.threads for s in t.steps}

    batch_id = uuid4()
    now = datetime.now(UTC).replace(tzinfo=None)
    history: list[FieldEdit] = []

    for edit in edits:
        if edit.target_kind == "walkthrough":
            if edit.field not in WALKTHROUGH_EDITABLE_FIELDS:
                raise EditValidationError(
                    f"Invalid walkthrough field: {edit.field}"
                )
            if edit.target_id != walkthrough.id:
                raise EditValidationError(
                    f"Walkthrough id mismatch: {edit.target_id} vs {walkthrough.id}"
                )
            old = getattr(walkthrough, edit.field) or ""
            if old == edit.value:
                continue
            setattr(walkthrough, edit.field, edit.value)
        elif edit.target_kind == "thread":
            if edit.field not in THREAD_EDITABLE_FIELDS:
                raise EditValidationError(
                    f"Invalid thread field: {edit.field}"
                )
            if edit.target_id not in thread_ids:
                raise EditValidationError(
                    f"Thread {edit.target_id} not in walkthrough"
                )
            thread = next(t for t in walkthrough.threads if t.id == edit.target_id)
            old = getattr(thread, edit.field) or ""
            if old == edit.value:
                continue
            setattr(thread, edit.field, edit.value)
        elif edit.target_kind == "step":
            if edit.field not in STEP_EDITABLE_FIELDS:
                raise EditValidationError(f"Invalid step field: {edit.field}")
            if edit.target_id not in step_ids:
                raise EditValidationError(
                    f"Step {edit.target_id} not in walkthrough"
                )
            step = next(
                s
                for t in walkthrough.threads
                for s in t.steps
                if s.id == edit.target_id
            )
            old = getattr(step, edit.field) or ""
            if old == edit.value:
                continue
            setattr(step, edit.field, edit.value)
            # Steps track their narration edit timestamp inline for fast UI hints.
            if edit.field == "narration":
                step.narration_edited_at = now
                step.narration_edited_by = editor
        else:
            raise EditValidationError(f"Unknown target_kind: {edit.target_kind}")

        history.append(
            FieldEdit(
                walkthrough_id=walkthrough.id,
                target_kind=edit.target_kind,
                target_id=edit.target_id,
                field=edit.field,
                old_value=old,
                new_value=edit.value,
                editor=editor,
                batch_id=batch_id,
            )
        )

    if history:
        session.add_all(history)
        await session.commit()
    return history


async def load_edit_history(
    session: AsyncSession, walkthrough_id: UUID
) -> list[FieldEdit]:
    stmt = (
        select(FieldEdit)
        .where(FieldEdit.walkthrough_id == walkthrough_id)
        .order_by(desc(FieldEdit.created_at))
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


def field_edit_to_dto(edit: FieldEdit) -> dict[str, Any]:
    return {
        "id": str(edit.id),
        "target_kind": edit.target_kind,
        "target_id": str(edit.target_id),
        "field": edit.field,
        "old_value": edit.old_value,
        "new_value": edit.new_value,
        "editor": edit.editor,
        "batch_id": str(edit.batch_id),
        "created_at": edit.created_at.isoformat() if edit.created_at else None,
    }
