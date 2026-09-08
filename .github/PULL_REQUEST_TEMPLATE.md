## What this PR does

<!-- One or two sentences. -->

## Why

<!-- What bug, false positive, missing coverage, or documentation gap prompted this? -->

## Affected component

- [ ] Scanner (`scripts/`)
- [ ] Agent prompt (`agents/`)
- [ ] Command (`commands/`)
- [ ] Data file (`data/`)
- [ ] Tests (`tests/`)
- [ ] Documentation
- [ ] Plugin registration (`.claude-plugin/plugin.json`)

## Evidence

<!-- Required for scanner heuristic changes. Cite confirmed findings (e.g. PYPYR-0012,
     PYPY-FUZZ-004), false-positive examples, or test-coverage rationale. -->

## Tests

```
pytest tests/ -v
```

<!-- Paste test summary, or note "all N tests pass". -->

## Checklist

- [ ] `pytest tests/ -v` passes
- [ ] New or changed scanner behaviour is covered by at least one new test
- [ ] No `__pycache__/` or generated output files in the diff
- [ ] JSON files are valid (`python -m json.tool <file>`)
- [ ] Scanner/agent/command names in documentation match actual filenames
- [ ] `WORKING_WITH_MAINTAINERS.md` guidance respected if findings reporting is affected
