---
name: Scanner improvement
about: Propose an improvement to a scanner's detection or precision
labels: scanner-improvement
---

## Scanner

<!-- Which scanner? E.g. "scan_translated_divergence.py" -->

## Problem / gap

<!-- What does the scanner currently miss, or flag incorrectly? Be specific about the bug class
     or pattern. -->

## Proposed improvement

<!-- Describe the heuristic change. A working implementation is welcome but not required. -->

## Currently missed — should be flagged

```python
# Minimal example the scanner currently misses but should catch.
# Note which PyPy source file(s) this pattern appears in, if known.
```

## Currently correct — must stay detected

```python
# Code the scanner correctly flags today and must continue to flag after the change.
```

## Currently flagged — should be skipped

```python
# Code the improvement would correctly stop flagging (new true negative).
```

## False-positive impact

<!-- Would this change increase or decrease false-positive volume? -->

## Evidence

<!-- Confirmed finding identifiers (e.g. PYPYR-0012, PYPY-FUZZ-004), PyPy source references,
     or static analysis results. An improvement without evidence that the pattern is real will
     take longer to review. -->
