# Working With Maintainers

`pypy-review-toolkit` is intended to help investigate potential issues in
PyPy's own implementation. The toolkit can surface useful candidates, but
automated findings are not automatically confirmed bugs.

The goal of a review is to produce evidence that is useful to maintainers:
a clear code path, a concrete explanation, and a reproducible demonstration
where practical.

## Review responsibly

Before beginning a large review campaign, understand the scope of the
project and its contribution and reporting practices.

Do not treat the number of findings produced by a scanner as a measure of
software quality. Static analysis intentionally trades completeness and
precision, and PyPy contains many deliberate implementation patterns that
can look suspicious to a generic checker.

A scanner finding should normally be treated as:

```text
candidate
   ↓
manual investigation
   ↓
reproduction / validation
   ↓
confirmed finding
```

## Distinguish confidence levels

Review results should clearly distinguish between:

- **Candidate** — a static pattern that deserves investigation.
- **Investigated** — the code path has been manually traced, but the
  behavior is not yet demonstrated.
- **Reproduced** — a minimal test or reproducer demonstrates the behavior.
- **Confirmed** — the behavior has been validated and determined to be a
  genuine issue rather than an intentional PyPy design or accepted
  limitation.

Do not present a candidate as a confirmed vulnerability or bug.

## Minimize false positives

PyPy uses RPython-specific conventions and implementation techniques that
are not necessarily valid assumptions in ordinary Python code.

Before reporting a finding, check:

- RPython translation semantics
- interpreter/object-space conventions
- JIT assumptions and annotations
- `we_are_translated()` behavior
- intentional guard patterns
- generated or translated code
- project-specific helper contracts
- existing tests
- recent git history

The presence of a pattern is evidence for investigation, not proof of a
defect.

## Prefer minimal reproducers

A good report should reduce the issue to the smallest practical example.

Prefer:

```text
large implementation detail
        ↓
small triggering condition
        ↓
minimal reproducer
```

A useful reproducer should identify:

- the PyPy version or commit tested
- the relevant configuration
- the triggering input
- the expected behavior
- the observed behavior
- relevant stderr/stdout or crash information

For crashes, preserve the exact observable failure whenever practical.

## Record the reviewed revision

Review findings are only meaningful in the context of a specific checkout.

Always record the PyPy revision used for the investigation:

```text
repository: pypy/pypy
branch/tag: <branch or tag>
commit: <commit SHA>
```

When comparing a finding against a released PyPy version, record that
version separately from the development checkout.

Do not assume that a finding discovered in one revision still exists in a
later revision.

## Check existing history

Before reporting a new issue, search the repository history and existing
issue tracker where practical.

A finding may already have:

- been fixed
- been discussed
- been intentionally accepted
- been reproduced under another issue
- been made obsolete by a larger refactor

The `git-history-analyzer` agent is useful for this stage.

## Security-sensitive findings

Do not publicly disclose details of an exploitable security issue through
a normal issue or pull request without considering the upstream project's
security-reporting process.

For a suspected security vulnerability:

1. establish that the behavior is real;
2. minimize the reproducer where possible;
3. identify the affected versions or revisions;
4. follow the upstream security disclosure process.

Avoid publishing weaponized exploit details when they are not necessary to
demonstrate the problem.

## Reporting a confirmed issue

A strong upstream report should normally contain:

### Summary

A short description of the defect.

### Affected revision

The exact PyPy version, branch, or commit tested.

### Trigger

The smallest practical reproducer.

### Observed behavior

The actual error, exception, crash, or incorrect result.

### Expected behavior

What should happen instead.

### Root cause

The relevant implementation path and why the behavior occurs.

### Impact

Explain the practical consequence without overstating severity.

### Evidence

Include useful logs, traces, or comparison results.

## Avoid noisy reports

Do not open one upstream issue for every low-confidence static match.

Group related findings only when they genuinely share:

- the same root cause;
- the same affected subsystem; or
- the same underlying bug pattern.

Otherwise, keep findings separate so maintainers can triage them independently.

## Working with upstream maintainers

The purpose of the toolkit is to help maintainers, not to overwhelm them.

Be precise, respectful, and open to correction.

A maintainer may identify an intentional invariant, translation rule, or
historical constraint that was not visible during static review.

That feedback is valuable. Update the finding and the toolkit's suppression
or recognition logic when appropriate.

## Feeding confirmed findings back into the toolkit

Confirmed findings should improve future reviews.

Where appropriate:

```text
confirmed issue
      ↓
reproducer
      ↓
regression test
      ↓
scanner/agent improvement
      ↓
known-good / known-bad example
```

False positives are also valuable. Record important non-bug patterns so
future scans can distinguish suspicious code from intentional PyPy idioms.

## Final principle

A useful review result is not:

> "The scanner found something."

It is:

> "The code path was investigated, the behavior was understood, and the
> evidence is strong enough for another engineer to verify the conclusion."

That is the standard this toolkit aims to support.
