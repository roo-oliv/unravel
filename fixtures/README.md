# Walkthrough fixtures

Drop walkthrough JSON files here to make them available to the web UI in
Phase 0.

## Generate

The CLI's `--json` flag emits the same `Walkthrough` schema the API
serves:

```bash
unravel pr 42 --json > fixtures/myrepo-pr-42.json
unravel pr roo-oliv/unravel#10 --json > fixtures/unravel-pr-10.json
```

The file stem (e.g. `myrepo-pr-42`) becomes the **slug** the API uses.
List endpoint returns slugs; load endpoint takes a slug:

```bash
curl -H "X-Dev-User: alice" http://localhost:8000/walkthroughs/fixture
curl -H "X-Dev-User: alice" http://localhost:8000/walkthroughs/fixture/myrepo-pr-42
```

## Variety matters for UI iteration

Aim for fixtures spanning sizes and shapes:

- **Small**: 5–10 hunks, 1–2 threads (typo fix, copy change)
- **Medium**: 20–40 hunks, 3–5 threads (feature add)
- **Large**: 80+ hunks, many threads with dependencies (refactor)
- **Cross-language**: TS + Python + SQL in one PR
- **Edge**: PR with renames, deletions, binary file noise

These shapes flush out edge cases in `<HunkView>`, `<ThreadList>`,
virtualization thresholds, and the dependency badge UI.

## Don't commit secrets

Real diff content can include sensitive code; review before committing
fixtures from private repos. For the demo set, prefer OSS PRs.
