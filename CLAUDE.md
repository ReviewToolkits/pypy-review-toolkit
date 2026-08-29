# CLAUDE.md — pypy-review-toolkit development guide

## Project overview

pypy-review-toolkit is a [Claude Code](https://docs.anthropic.com/en/docs/claude-code) plugin for
statically reviewing **PyPy's own RPython-level implementation** — the interpreter core, object
space, and JIT — for correctness bugs and translation hazards specific to how PyPy is built.

Sibling of [cpython-review-toolkit](https://github.com/ReviewToolkits/cpython-review-toolkit) and
[rustpy-review-toolkit](https://github.com/ReviewToolkits/rustpy-review-toolkit). Reviews PyPy's
own source, not code that runs on PyPy, and not the CPython-compatible stdlib PyPy ships in
`lib-python/` / `lib_pypy/` (except `lib_pypy/` CFFI/free-pairing checks).

Bugs found by this toolkit are catalogued in
[devdanzin/pypy-review-findings](https://github.com/devdanzin/pypy-review-findings).

## Prerequisites

- Python 3.x host (the toolkit runs on CPython to analyse PyPy's source)
- `tree-sitter` and `tree-sitter-python`: `pip install -r requirements.txt`

**tree-sitter is not optional.** PyPy's RPython source is written in Python 2 syntax on every
branch — the `py3.x` branches implement Python 3 at the application level; they are not *written*
in it. Without tree-sitter, files that fail `ast.parse()` under a Python 3 host are silently
skipped. Measured on `py3.11` (`fe2af5843a`): 8.5%–29.0% of `.py` files per layer.

A PyPy source checkout to analyse — the user provides the path; nothing is bundled. PyPy's
repository is at <https://github.com/pypy/pypy>; the `py3.11` branch is the primary target.

## Dev commands

```bash
# Install all dependencies (tree-sitter, tree-sitter-python, pytest)
pip install -r requirements.txt

# Run all tests
pytest tests/ -v

# Run tests for a specific scanner
pytest tests/test_scan_translated_divergence.py -v
pytest tests/test_scan_guard_callback_deref.py -v

# Run a scanner standalone (all output JSON to stdout)
python plugins/pypy-review-toolkit/scripts/scan_translated_divergence.py /path/to/pypy
python plugins/pypy-review-toolkit/scripts/scan_guard_callback_deref.py /path/to/pypy/pypy/module

# Validate JSON files
python -m json.tool plugins/pypy-review-toolkit/.claude-plugin/plugin.json
python -m json.tool .claude-plugin/marketplace.json

# Load the plugin without a marketplace install
claude --plugin-dir plugins/pypy-review-toolkit
```

## Code style

- Python 3.x (`X | Y` unions, type hints on all signatures, docstrings on public functions)
- Double quotes for strings
- Tests use `pytest` — not unittest
- Scanners output JSON to stdout; no print statements outside `main()`
- No bare `import *`

## Project structure

This is a Claude Code plugin, not a pip-installable package.

```
pypy-review-toolkit/
├── CLAUDE.md                                   # This file
├── README.md                                   # User-facing documentation
├── CONTRIBUTING.md
├── WORKING_WITH_MAINTAINERS.md                 # Social contract — read this
├── LICENSE
├── requirements.txt
├── .claude-plugin/marketplace.json
├── docs/
│   ├── pypy-review-toolkit-design.md           # Authoritative spec
│   ├── pypy-review-toolkit-MASTER-REPORT.md
│   ├── pypy-review-toolkit-plan-report.md
│   └── PYPY_FINDINGS_REPORT.md                 # Confirmed findings catalogue
├── plugins/pypy-review-toolkit/
│   ├── .claude-plugin/plugin.json              # Canonical agent + command list
│   ├── agents/                                 # 7 agent prompts (.md files)
│   ├── commands/                               # 4 command definitions (.md files)
│   ├── data/                                   # Data files (known_bugs.tsv, etc.)
│   └── scripts/                               # 9 scanner scripts (.py files)
└── tests/                                      # pytest test suite (112 tests)
```

## Architecture

### Scripts (the core analysis code)

All scripts live in `plugins/pypy-review-toolkit/scripts/`. Every scanner follows the same pattern:
parse PyPy source with tree-sitter + `ast.parse()` fallback, find candidate issues, output JSON to
stdout.

| Script | Purpose |
|--------|---------|
| `scan_translated_divergence.py` | `we_are_translated()` arm divergence — **flagship** |
| `scan_immutability_contracts.py` | `_immutable_fields_` / `@jit.elidable` mismatches — **crown jewel** |
| `scan_interp_app_boundary.py` | `OperationError` leaks at the interp/app boundary |
| `scan_rpython_restrictions.py` | RPython restrictions (unbounded `**kwargs`, etc.) |
| `scan_unvalidated_helper_calls.py` | User values into RPython helpers without precondition checks |
| `scan_sibling_guard_consistency.py` | App-exposed method missing the guard its sibling class uses |
| `scan_cross_class_method_guard.py` | Same method name on sibling classes; guard missing on one |
| `scan_free_pairing.py` | Raw `free()` pairing and suspicious `ffi.*` access in `lib_pypy/` |
| `scan_guard_callback_deref.py` | Guard → callback → guarded-field dereference (TOCTOU) |

**Script calling convention:** every scanner exposes `analyze(target, *, max_files=0) -> dict` and
a `main()` that outputs JSON to stdout. The JSON envelope must include a `pypy_info` block carrying
`degraded_parse_mode: true` when tree-sitter is unavailable.

**Data files** in `plugins/pypy-review-toolkit/data/`:

- `known_bugs.tsv` — the known-bugs catalogue consumed by the `known-issues` command; imported from
  [devdanzin/pypy-review-findings](https://github.com/devdanzin/pypy-review-findings). Do not
  hand-edit.

### Agents

7 markdown files in `plugins/pypy-review-toolkit/agents/`. Each has YAML frontmatter (name,
description, model, color) and a structured prompt. Agents run scanner scripts, read JSON output,
then perform deep qualitative review of each candidate finding. Scanners find candidates (high
recall, expect false positives); agents confirm or dismiss each by reading the real code.

| Agent | Script | Focus |
|-------|--------|-------|
| `translated-divergence-auditor` | `scan_translated_divergence.py` | `we_are_translated()` arm asymmetry |
| `immutability-contract-auditor` | `scan_immutability_contracts.py` | `_immutable_fields_` / `@jit.elidable` violations |
| `interp-app-boundary-checker` | `scan_interp_app_boundary.py` | `OperationError` escape to app level |
| `rpython-restriction-scanner` | `scan_rpython_restrictions.py` | RPython restriction violations |
| `unvalidated-helper-call-auditor` | `scan_unvalidated_helper_calls.py` | Missing precondition checks |
| `jit-trace-reviewer` | (qualitative) | JIT trace correctness and elidable contract |
| `git-history-analyzer` | (qualitative) | Similar unfixed bugs, churn prioritization |

The canonical agent list is in `plugins/pypy-review-toolkit/.claude-plugin/plugin.json`. Always
verify from that file, not from documentation.

### Commands

4 markdown files in `plugins/pypy-review-toolkit/commands/`:

- `explore.md` — full phased review: discovery → scanner pass → agent triage → synthesis
- `health.md` — quick scored 1–10 dashboard across every dimension
- `hotspots.md` — rank the riskiest locations (divergence + immutability + guard gaps)
- `known-issues.md` — cross-reference the known-bugs catalogue against a fresh scanner run

### Classification system

Every finding is tagged:

| Tag | Meaning | Example |
|-----|---------|---------|
| **FIX** | Bug causing wrong behaviour, crash, or `SystemError` | `OperationError` escaping to app level |
| **CONSIDER** | Likely improvement, may need design discussion | Guard present in 3 of 4 sibling methods |
| **POLICY** | Design decision for the PyPy maintainers — their call | Whether to restrict a `**kwargs` surface |
| **ACCEPTABLE** | Noted, no action needed | Intentional `we_are_translated()` asymmetry |

`POLICY` items are not "things you should push the maintainer to fix". See
`WORKING_WITH_MAINTAINERS.md` for severity-translation guidance.

## RPython / PyPy-specific constraints

**PyPy's source is written in Python 2 syntax.** The `py3.x` branches implement Python 3 at the
application level; the interpreter itself is RPython. A host tool that fails on Python 2 syntax
silently misses the interpreter core.

Key concepts required before touching any scanner:

- **`we_are_translated()`** — returns `False` on CPython, `True` after RPython translation. The
  translated-divergence scanner's working hypothesis is that asymmetry between the two arms is the
  dominant confirmed-bug class (295 findings on `py3.11`; `PYPYR-0014` is the first confirmed
  instance of the interp/app escape shape).
- **`_immutable_fields_`** — RPython annotation marking fields as JIT-elidable. A field listed as
  immutable but mutated after construction corrupts JIT traces silently.
- **`@jit.elidable`** — marks a function as side-effect-free and foldable under the JIT. An
  elidable function with side effects or that calls non-elidable functions is a correctness bug.
- **`OperationError`** — the interpreter-level wrapper for Python exceptions. An `OperationError`
  that escapes to app-level code without being converted becomes a `SystemError`. The interp-app
  scanner leads with the same-function-asymmetry signal.
- **`W_` prefix** — wrapped objects at the application level (`W_BytesIO`, `W_StringIO`,
  `W_MemoryView`). Guard patterns on `W_` classes are the subject of the sibling-guard and
  cross-class-method-guard scanners.
- **`ffi.NULL` vs `ffi.NONE`** — in `lib_pypy/` CFFI code, `ffi.NONE` is a typo for `ffi.NULL`;
  the free-pairing scanner catches this class (PYPY-FUZZ-004).

**Tree-sitter degraded parse mode:** when `tree_sitter_python` is not importable, files that use
Python 2 syntax are silently skipped. The scanner envelope must carry `degraded_parse_mode: true` in
`pypy_info` (not a bare `"tree_sitter_available": false` flag). Never suppress this warning.

## Testing notes

- Test suite lives in `tests/`; runner is `pytest`
- 112 tests must pass; run `pytest tests/ -v` before any PR
- Tests create temporary directories with synthetic PyPy-like `.py` files, run scanners on them, and
  check the JSON output
- Every scanner test must cover: a true positive from a confirmed finding or representative pattern;
  a true negative; at least one RPython/Python 2 edge case (print statement, `we_are_translated()`
  guard, `_immutable_fields_`, `W_` class, etc.)
- Test files are named `test_scan_<scanner_name>.py` matching the scanner they cover

## Adding a new scanner

1. Create `plugins/pypy-review-toolkit/scripts/scan_<newcheck>.py`
2. Implement `analyze(target, *, max_files=0) -> dict`; output JSON to stdout via `main()`
3. Carry `degraded_parse_mode` in the `pypy_info` envelope when tree-sitter is unavailable
4. Create `tests/test_scan_<newcheck>.py` with true positive, true negative, RPython edge case
5. Create `plugins/pypy-review-toolkit/agents/<newcheck>-auditor.md` with YAML frontmatter
6. Add the agent to the appropriate phase in `commands/explore.md`
7. Register the agent in `plugins/pypy-review-toolkit/.claude-plugin/plugin.json`
8. Update `README.md` to list the scanner

## Adding a new agent (qualitative, no scanner)

1. Create `plugins/pypy-review-toolkit/agents/<name>.md` with YAML frontmatter
2. The agent prompt should instruct Claude Code to use Grep/Read tools directly
3. Add to the appropriate phase in `commands/explore.md`
4. Register in `plugins/pypy-review-toolkit/.claude-plugin/plugin.json`

## Gotchas

- **PyPy's RPython source is Python 2 syntax, not Python 3.** Calling `ast.parse()` without
  tree-sitter on RPython source will silently skip 8.5%–29.0% of files depending on the layer.
  The `degraded_parse_mode` flag exists precisely because this silence is dangerous — a scan that
  looks complete may have missed the entire interpreter core.

- **`we_are_translated()` branches are not symmetric by design — sometimes.** The scanner flags
  asymmetry as a candidate, not a confirmed bug. The agent reads the actual code to determine
  whether the asymmetry is intentional (e.g., debug-only code on the untranslated arm) or a real
  divergence (e.g., an error path that exists only on the untranslated arm).

- **`_immutable_fields_` inheritance is non-trivial.** A subclass that does not redeclare
  `_immutable_fields_` inherits its parent's list. The immutability scanner must track inheritance
  chains, not just per-class declarations.

- **`fixedunpack` and similar are correctly ACCEPTABLE.** `scan_interp_app_boundary.py` flags
  `pyframe.py:236` and correctly marks `fixedunpack` as `ACCEPTABLE` — the `OperationError` is
  handled before propagation. Do not regress this.

- **`ffi.NONE` is a real typo, not a variable name.** In `lib_pypy/`, `ffi.NONE` does not exist;
  the correct attribute is `ffi.NULL`. The free-pairing scanner catches this (PYPY-FUZZ-004).

- **`known_bugs.tsv` is imported, not edited here.** Changes to the findings catalogue belong in
  [devdanzin/pypy-review-findings](https://github.com/devdanzin/pypy-review-findings); the TSV in
  this repository is a downstream import. Do not hand-edit it.

- **Do not commit `__pycache__/` entries or scanner JSON output.** These are covered by
  `.gitignore`; verify before committing.

- **`plugin.json` is the canonical agent/command list.** If documentation and `plugin.json`
  disagree, `plugin.json` wins.

## Design document

`docs/pypy-review-toolkit-design.md` is the authoritative spec — the bug classes, scanner designs,
JSON envelope format, FIX/CONSIDER/POLICY/ACCEPTABLE classification, and the `we_are_translated()`
working hypothesis. Read it before changing any scanner heuristic.

`docs/PYPY_FINDINGS_REPORT.md` is the ground-truth findings catalogue. A scanner change that
reduces recall on a confirmed finding in this file is a regression.
