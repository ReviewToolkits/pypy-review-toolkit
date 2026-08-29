---
name: False positive
about: Report a location that a scanner incorrectly flags
labels: false-positive
---

## Scanner

<!-- Which scanner? E.g. "scan_translated_divergence.py" -->

## Flagged location

<!-- File path and line number as reported by the scanner. E.g. "pypy/interpreter/pyframe.py:236" -->

## Why this is a false positive

<!-- Explain why the flagged code is correct. Is this a deliberate RPython pattern? Is the guard
     or precondition present elsewhere? Is the `we_are_translated()` branch intentionally
     asymmetric? Does `_immutable_fields_` or `@jit.elidable` apply correctly despite the apparent
     mismatch? Is the `OperationError` correctly wrapped before propagation? -->

## Source context

```python
# Paste enough source to confirm the false positive without a full checkout.
```

## Scanner output

```json
// Paste the relevant JSON finding or agent classification.
```

## PyPy branch and commit

## Suggested heuristic fix (optional)

<!-- If you know what change would eliminate this false positive without eliminating nearby true
     positives, describe it here. A PR is welcome but not required. -->
