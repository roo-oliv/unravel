"""Domain data classes for Unravel walkthroughs."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Literal

SourceKind = Literal["pr", "commit", "range", "branch", "staged"]


@dataclass
class SourceInfo:
    """Describes the origin of the diff being analyzed.

    Used by the TUI header to show a one-line summary of what's under review:
    repo + PR number/title, short SHA + subject, branch name, or commit count.
    """

    kind: SourceKind
    label: str
    repo: str | None = None
    detail: str | None = None

EXTENSION_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".rb": "ruby",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".kt": "kotlin",
    ".scala": "scala",
    ".c": "c",
    ".cpp": "cpp",
    ".h": "c",
    ".hpp": "cpp",
    ".cs": "csharp",
    ".swift": "swift",
    ".m": "objectivec",
    ".php": "php",
    ".lua": "lua",
    ".sh": "bash",
    ".bash": "bash",
    ".zsh": "zsh",
    ".fish": "fish",
    ".sql": "sql",
    ".html": "html",
    ".css": "css",
    ".scss": "scss",
    ".less": "less",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".toml": "toml",
    ".xml": "xml",
    ".md": "markdown",
    ".r": "r",
    ".R": "r",
    ".ex": "elixir",
    ".exs": "elixir",
    ".erl": "erlang",
    ".hs": "haskell",
    ".ml": "ocaml",
    ".clj": "clojure",
    ".dart": "dart",
    ".vue": "vue",
    ".svelte": "svelte",
    ".tf": "hcl",
    ".proto": "protobuf",
    ".graphql": "graphql",
    ".gql": "graphql",
}


@dataclass
class Hunk:
    file_path: str = ""
    old_start: int = 0
    old_count: int = 0
    new_start: int = 0
    new_count: int = 0
    content: str = ""
    context_before: str = ""
    context_after: str = ""
    language: str | None = None
    id: str = ""
    additions: int = 0
    deletions: int = 0
    caption: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "file_path": self.file_path,
            "old_start": self.old_start,
            "old_count": self.old_count,
            "new_start": self.new_start,
            "new_count": self.new_count,
            "content": self.content,
            "context_before": self.context_before,
            "context_after": self.context_after,
            "language": self.language,
            "additions": self.additions,
            "deletions": self.deletions,
            "caption": self.caption,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Hunk:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class ThreadStep:
    hunks: list[Hunk]
    narration: str
    order: int

    def to_dict(self) -> dict:
        return {
            "hunks": [h.to_dict() for h in self.hunks],
            "narration": self.narration,
            "order": self.order,
        }

    @classmethod
    def from_dict(cls, data: dict) -> ThreadStep:
        return cls(
            hunks=[_parse_hunk_ref(h) for h in data["hunks"]],
            narration=data["narration"],
            order=data["order"],
        )


@dataclass
class Thread:
    id: str
    title: str
    summary: str
    root_cause: str
    steps: list[ThreadStep]
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "summary": self.summary,
            "root_cause": self.root_cause,
            "steps": [s.to_dict() for s in self.steps],
            "dependencies": self.dependencies,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Thread:
        return cls(
            id=data["id"],
            title=data["title"],
            summary=data["summary"],
            root_cause=data["root_cause"],
            steps=[ThreadStep.from_dict(s) for s in data["steps"]],
            dependencies=data.get("dependencies", []),
        )


@dataclass
class Walkthrough:
    threads: list[Thread]
    overview: str
    suggested_order: list[str]
    raw_diff: str = ""
    metadata: dict = field(default_factory=dict)
    hunk_captions: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "threads": [t.to_dict() for t in self.threads],
            "overview": self.overview,
            "suggested_order": self.suggested_order,
            "metadata": self.metadata,
            "hunk_captions": self.hunk_captions,
        }

    @classmethod
    def from_dict(cls, data: dict, raw_diff: str = "") -> Walkthrough:
        return cls(
            threads=[Thread.from_dict(t) for t in data["threads"]],
            overview=data["overview"],
            suggested_order=data["suggested_order"],
            raw_diff=raw_diff,
            metadata=data.get("metadata", {}),
            hunk_captions=data.get("hunk_captions", {}),
        )

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    @classmethod
    def from_json(cls, text: str, raw_diff: str = "") -> Walkthrough:
        return cls.from_dict(json.loads(text), raw_diff=raw_diff)


def _parse_hunk_ref(ref: str | dict) -> Hunk:
    """Parse a hunk reference from the LLM response.

    The schema expects a string ID (e.g., "H7"), but we also accept a dict for
    backward compatibility with hand-written tests and older fixtures.
    """
    if isinstance(ref, str):
        return Hunk(id=ref)
    return Hunk.from_dict(ref)


WALKTHROUGH_JSON_SCHEMA: dict = {
    "type": "object",
    "required": ["threads", "overview", "suggested_order", "hunk_captions"],
    "properties": {
        "overview": {
            "type": "string",
            "description": "A 2-4 sentence summary of the entire change set.",
        },
        "suggested_order": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Thread IDs in recommended review order (foundational first).",
        },
        "hunk_captions": {
            "type": "object",
            "additionalProperties": {"type": "string"},
            "description": (
                "Map of every hunk ID (e.g., 'H1') to a short 2-5 word "
                "one-liner describing WHAT the hunk contains at a glance "
                "(not why). Examples: 'New imports', 'Imports update', "
                "'New createFooBar function', 'getFooBar signature update', "
                "'Constants update', 'New X enum item'. Coverage is "
                "mandatory: every hunk ID must appear as a key."
            ),
        },
        "threads": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title", "summary", "root_cause", "steps"],
                "properties": {
                    "id": {
                        "type": "string",
                        "description": "Short kebab-case slug, e.g. 'add-retry-logic'.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Human-readable title for this thread.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "What this thread accomplishes and why.",
                    },
                    "root_cause": {
                        "type": "string",
                        "description": "The driving motivation or root cause behind these changes.",
                    },
                    "dependencies": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "IDs of threads that should be reviewed before this one.",
                    },
                    "steps": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "required": ["hunks", "narration", "order"],
                            "properties": {
                                "order": {
                                    "type": "integer",
                                    "description": "1-based step order within the thread.",
                                },
                                "narration": {
                                    "type": "string",
                                    "description": (
                                        "Explanation of what this step does and why, "
                                        "written as a knowledgeable colleague."
                                    ),
                                },
                                "hunks": {
                                    "type": "array",
                                    "items": {
                                        "type": "string",
                                        "description": (
                                            "Hunk ID from the File Summary "
                                            "(e.g., 'H7'). Must match exactly."
                                        ),
                                    },
                                    "description": (
                                        "IDs of hunks belonging to this step. "
                                        "Every hunk ID must appear in at least "
                                        "one step across all threads."
                                    ),
                                },
                            },
                        },
                    },
                },
            },
        },
    },
}
