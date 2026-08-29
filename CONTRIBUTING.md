# Contributing to pypy-review-toolkit

Thanks for your interest in contributing. Read `CLAUDE.md` for the dev-command reference and
architecture overview. Read `WORKING_WITH_MAINTAINERS.md` before using toolkit findings on a
project you don't own.

---

## Setup

```bash
# Clone and install
git clone https://github.com/ReviewToolkits/pypy-review-toolkit.git
cd pypy-review-toolkit
pip install -r requirements.txt        # tree-sitter, tree-sitter-python, pytest
```

**tree-sitter is not optional.** Without it, scanners silently skip 8.5%–29.0% of PyPy's source
files per layer (RPython is Python 2 syntax; `ast.parse()` under Python 3 fails on those files).

You will also want a local PyPy checkout to run scanners against real input:

```bash
git clone https://github.com/pypy/pypy.git
git -C pypy checkout py3.11
```

---

## Running tests

```bash
pytest tests/ -v                                       # full suite — must all pass
pytest tests/test_scan_translated_divergence.py -v     # single scanner
```

112 tests must pass. If a scanner change causes failures, fix them or update them with an
explanation before opening a PR.

---

## Running scanners manually

```bash
python plugins/pypy-review-toolkit/scripts/scan_translated_divergence.py /path/to/pypy
python plugins/pypy-review-toolkit/scripts/scan_guard_callback_deref.py /path/to/pypy/pypy/module
```

All scanners output JSON to stdout.

---

## Before changing a scanner

1. Read the relevant section of `docs/pypy-review-toolkit-design.md` (the authoritative spec).
2. Check `docs/PYPY_FINDINGS_REPORT.md` — do not reduce recall on any confirmed finding.
3. Run the scanner's test file before and after your change.
4. Understand what the scanner is doing and why before touching it.

Do not change a heuristic without a test demonstrating the before/after behaviour. Do not claim a
scanner catches a new bug class without a confirming example.

---

## Adding a new scanner

See `CLAUDE.md — Adding a new scanner` for the step-by-step. Short version: scanner script →
test file → agent prompt → `plugin.json` registration → `README.md` update.

Every new scanner needs:
- A true positive from a confirmed finding or representative PyPy source pattern
- A true negative
- At least one RPython-specific edge case (Python 2 syntax, `we_are_translated()`, `W_` class,
  `_immutable_fields_`, etc.)

---

## Handling false positives

False positives are expected — the scanners are high-recall, not high-precision. Agents classify
candidates; `ACCEPTABLE` is a valid outcome, not a failure.

If you believe a scanner produces a systematic false positive:

1. Open an issue using `.github/ISSUE_TEMPLATE/false_positive.md`
2. Include the scanner name, flagged location, source context, and a mechanistic argument for why
   the pattern is benign
3. If you have a heuristic fix, include it and open a PR with tests

Do not silently add suppressions without a corresponding test and explanation.

---

## Adding new known findings

Confirmed findings belong in
[devdanzin/pypy-review-findings](https://github.com/devdanzin/pypy-review-findings). The
`data/known_bugs.tsv` in this repository is imported from that catalogue — do not hand-edit it.

A finding must have one of the following before being catalogued:

- **Reproduced crash** — a minimal Python-level reproducer with captured output (SIGSEGV,
  `SystemError`, wrong result, etc.) on a real PyPy build
- **Static-confirmed location** — a mechanistic argument ("X calls Y on Z without checking Q,
  and the absence of Q causes W") documented in `docs/PYPY_FINDINGS_REPORT.md`

"Plausible but unconfirmed" is not enough.

---

## Evidence requirements

Scanner heuristic changes, new findings, and agent classification changes all require evidence.
Evidence is one of:

- A confirmed finding identifier (e.g. `PYPYR-0012`, `PYPY-FUZZ-004`)
- A false-positive analysis showing a pattern is never a real defect
- A test-coverage argument for a neutral refactor

PRs that change scanner output without evidence will be asked to provide it.

---

## Pull requests

Before opening a PR:

```bash
pytest tests/ -v                                      # all tests must pass
python -m json.tool plugins/pypy-review-toolkit/.claude-plugin/plugin.json   # valid JSON
python -m json.tool .claude-plugin/marketplace.json
```

Fill out `.github/PULL_REQUEST_TEMPLATE.md`. PRs that change scanner heuristics, add scanners, or
modify agent prompts must include updated tests. PRs that only change documentation still need the
checklist completed.

---

## Commit and branch conventions

- Branch off `main`: `fix/<description>`, `feat/<description>`, `docs/<description>`
- Commit messages: imperative mood, subject + body explaining *why*
  - Good: `fix(scan_interp_app_boundary): narrow OperationError false positive on fixedunpack`
  - Bad: `update scanner`
- Do not commit `__pycache__/`, scanner JSON output, or generated reports
- Do not commit unless a maintainer asks you to

---

## Review process

PRs are reviewed by the project maintainers. Expect:

- Requests for evidence when a heuristic changes without a confirming finding
- Requests to update tests if coverage is insufficient
- Requests to narrow scope if a PR mixes unrelated changes

Respond to review comments promptly. A maintainer verdict of `ACCEPTABLE` or `POLICY` on a finding
is a complete answer; do not relitigate it.

---

## Security / correctness-sensitive findings

If a scanner surfaces a reproducible crash or memory-safety bug in PyPy:

- Check [pypy/pypy issues](https://github.com/pypy/pypy/issues) and
  [devdanzin/pypy-review-findings](https://github.com/devdanzin/pypy-review-findings) for duplicates
  first
- Follow PyPy's contribution and security disclosure process for bugs with security implications
- Crashes reachable from attacker-controlled input belong in a private disclosure channel, not a
  public issue

---

## Generated files — do not commit

- `__pycache__/` directories and `.pyc` files
- Scanner JSON output produced by running scripts manually
- Report files generated by `explore`, `health`, or `hotspots` commands
- Local environment files (`.env`, virtual environment directories)

These are covered by `.gitignore`. If you find a tracked generated file, add it to `.gitignore`
in a separate PR.
