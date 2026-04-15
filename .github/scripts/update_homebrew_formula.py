#!/usr/bin/env python3
"""Merge freshly-generated Homebrew resource blocks into the tap's formula.

Usage:
    update_homebrew_formula.py <poet-output.rb> <target-formula.rb>

Reads a formula produced by `homebrew-pypi-poet -f unravel-review` from the
first argument and rewrites the second argument in place. The target formula
keeps its class name, header comments, desc, homepage, license, head ref,
depends_on, install, and test sections; only the top-level `url`/`sha256` and
the block of `resource` entries are replaced.

Exits non-zero (without writing) if either the poet output or the target
formula does not match the expected shape — this is the whole point of having
a dedicated script rather than a sed one-liner.
"""
from __future__ import annotations

import pathlib
import re
import sys

# --- poet output extraction -----------------------------------------------
# The top-level unravel_review sdist. The filename has an underscore because
# PyPI normalises dashes in stored filenames.
POET_MAIN_URL_SHA = re.compile(
    r'^  url "(https://files\.pythonhosted\.org/[^"]+/unravel_review-[^"]+)"\n'
    r'  sha256 "([0-9a-f]{64})"',
    re.M,
)

# A single resource block as emitted by poet. The two-space indent identifies
# a resource at formula scope; the four-space indent on url/sha256 identifies
# its body.
POET_RESOURCE_BLOCK = re.compile(
    r'^  resource "[^"]+" do\n'
    r'    url "[^"]+"\n'
    r'    sha256 "[0-9a-f]{64}"\n'
    r'  end\n',
    re.M,
)

# --- target formula surgery -----------------------------------------------
FORMULA_MAIN_URL_SHA = re.compile(
    r'^  url "[^"]+"\n  sha256 "[0-9a-f]{64}"',
    re.M,
)

# Span between the `depends_on "python@3.12"` line and the `def install` line.
# Using a non-greedy .*? with DOTALL lets it span the blank lines and every
# resource entry. The lookbehind/lookahead keep the anchors out of the match
# so the `re.sub` replacement only rewrites the resources themselves.
FORMULA_RESOURCES_SPAN = re.compile(
    r'(?<=^  depends_on "python@3\.12"\n)'
    r'.*?'
    r'(?=^  def install\b)',
    re.M | re.DOTALL,
)


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    poet_path = pathlib.Path(sys.argv[1])
    formula_path = pathlib.Path(sys.argv[2])

    poet = poet_path.read_text()
    formula = formula_path.read_text()

    main_match = POET_MAIN_URL_SHA.search(poet)
    if not main_match:
        print("ERROR: main url/sha256 not found in poet output", file=sys.stderr)
        return 1
    main_url, main_sha = main_match.group(1), main_match.group(2)

    resource_blocks = POET_RESOURCE_BLOCK.findall(poet)
    if not resource_blocks:
        print("ERROR: no resource blocks found in poet output", file=sys.stderr)
        return 1

    # Homebrew audit requires the resource name to match the PyPI canonical
    # name, which uses dashes. Poet emits the sdist filename stem (e.g.
    # "pydantic_core"), so normalise underscores → dashes in the resource
    # name only (leaving urls/sha256 untouched).
    def _dashify(block: str) -> str:
        return re.sub(
            r'^(  resource ")([^"]+)(" do)',
            lambda m: m.group(1) + m.group(2).replace("_", "-") + m.group(3),
            block,
            count=1,
            flags=re.M,
        )

    resource_blocks = [_dashify(b) for b in resource_blocks]

    # Stitch the resource blocks back together with blank lines between them,
    # matching the style poet itself uses.
    new_resources = "\n" + "\n".join(block.rstrip() + "\n" for block in resource_blocks) + "\n"

    # Swap the main url/sha256.
    formula_after_url, url_subs = FORMULA_MAIN_URL_SHA.subn(
        f'  url "{main_url}"\n  sha256 "{main_sha}"',
        formula,
        count=1,
    )
    if url_subs != 1:
        print("ERROR: main url/sha256 pattern not found in target formula", file=sys.stderr)
        return 1

    # Swap the resource span.
    formula_after_resources, res_subs = FORMULA_RESOURCES_SPAN.subn(
        new_resources,
        formula_after_url,
        count=1,
    )
    if res_subs != 1:
        print("ERROR: resource span not found in target formula", file=sys.stderr)
        return 1

    formula_path.write_text(formula_after_resources)
    print(
        f"Updated {formula_path} — main url {main_url.rsplit('/', 1)[-1]}, "
        f"{len(resource_blocks)} resources."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
