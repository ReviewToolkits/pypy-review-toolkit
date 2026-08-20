"""Detect guard -> app-level callback -> guarded-field dereference patterns."""

from __future__ import annotations

import ast
from pathlib import Path


def _self_field(node: ast.AST) -> str | None:
    if (
        isinstance(node, ast.Attribute)
        and isinstance(node.value, ast.Name)
        and node.value.id == "self"
    ):
        return node.attr
    return None


def _guarded_fields_from_call(node: ast.Call) -> set[str]:
    """Return fields established by a self._check_* guard call."""
    func = node.func

    if not isinstance(func, ast.Attribute):
        return set()

    if not (
        isinstance(func.value, ast.Name)
        and func.value.id == "self"
    ):
        return set()

    guard_fields = {
        "_check_attached": {"w_buffer"},
        "_check_closed": {"w_buffer"},
        "_check_init": {"w_buffer"},
    }

    return guard_fields.get(func.attr, set())


def _inline_guarded_fields(node: ast.If) -> set[str]:
    """Return self fields checked by simple truthiness guards."""
    test = node.test

    if isinstance(test, ast.Attribute):
        field = _self_field(test)
        if field is not None:
            return {field}

    if isinstance(test, ast.UnaryOp) and isinstance(test.op, ast.Not):
        operand = test.operand
        if isinstance(operand, ast.Attribute):
            field = _self_field(operand)
            if field is not None:
                return {field}

    return set()


def _callback_kind(node: ast.Call) -> str | None:
    """Classify calls capable of re-entering app-level Python."""
    func = node.func

    if not isinstance(func, ast.Attribute):
        return None

    if not (
        isinstance(func.value, ast.Name)
        and func.value.id == "space"
    ):
        return None

    if func.attr == "call_method":
        if node.args:
            target = node.args[0]

            if isinstance(target, ast.Name) and target.id == "self":
                return "self-dispatch"

            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
            ):
                return "internal-object-dispatch"

        return "app-dispatch"

    if func.attr in {
        "call_function",
        "getattr",
        "next",
    }:
        return "app-dispatch"

    return None


def _dereferenced_fields(node: ast.AST) -> set[str]:
    """Return guarded self fields used by an expression."""
    fields: set[str] = set()

    for child in ast.walk(node):
        if isinstance(child, ast.Attribute):
            field = _self_field(child)
            if field is not None:
                fields.add(field)

    return fields


def _callback_deref_reason(
    callback_kind: str | None,
) -> tuple[str, str]:
    if callback_kind == "self-dispatch":
        return (
            "CONSIDER",
            "guard-callback-deref: self-dispatch may "
            "invalidate the guarded field before it is "
            "dereferenced",
        )

    return (
        "CONSIDER",
        "guard-callback-deref: app-level callback may "
        "invalidate the guarded field before it is "
        "dereferenced",
    )


def _is_dereference_expression(node: ast.AST) -> bool:
    """Return whether an expression actually uses a self field."""
    if isinstance(node, ast.Attribute):
        return _self_field(node) is not None

    if isinstance(node, ast.Call):
        return bool(_dereferenced_fields(node))

    return False


def _calls_in_expression(node: ast.AST) -> list[ast.Call]:
    return [
        child
        for child in ast.walk(node)
        if isinstance(child, ast.Call)
    ]


def _statement_expressions(node: ast.stmt) -> list[ast.AST]:
    """Return expressions evaluated by a statement."""
    if isinstance(node, ast.Assign):
        return [node.value]

    if isinstance(node, ast.AnnAssign):
        return [node.value] if node.value is not None else []

    if isinstance(node, ast.AugAssign):
        return [node.target, node.value]

    if isinstance(node, ast.Expr):
        return [node.value]

    if isinstance(node, ast.Return):
        return [node.value] if node.value is not None else []

    if isinstance(node, ast.Raise):
        expressions: list[ast.AST] = []

        if node.exc is not None:
            expressions.append(node.exc)

        if node.cause is not None:
            expressions.append(node.cause)

        return expressions

    if isinstance(node, ast.Assert):
        expressions = [node.test]

        if node.msg is not None:
            expressions.append(node.msg)

        return expressions

    return []


def _guard_calls_in_expression(node: ast.AST) -> set[str]:
    fields: set[str] = set()

    for call in _calls_in_expression(node):
        fields.update(_guarded_fields_from_call(call))

    return fields


def _callback_calls_in_expression(node: ast.AST) -> list[str]:
    kinds: list[str] = []

    for call in _calls_in_expression(node):
        kind = _callback_kind(call)
        if kind is not None:
            kinds.append(kind)

    return kinds


def _contains_guarded_dereference(
    expression: ast.AST,
    guarded_fields: set[str],
) -> bool:
    """Return whether an expression dereferences a guarded self field."""
    if not guarded_fields:
        return False

    if isinstance(expression, ast.Attribute):
        field = _self_field(expression)
        return field in guarded_fields

    if isinstance(expression, ast.Call):
        return bool(
            guarded_fields.intersection(
                _dereferenced_fields(expression)
            )
        )

    return False

def _classify_block(
    statements: list[ast.stmt],
    guarded_fields: set[str],
    saw_callback: bool = False,
    callback_kind: str | None = None,
) -> tuple[str | None, str | None]:
    """Recursively classify a statement block."""
    for node in statements:
        if isinstance(node, ast.If):
            inline_fields = _inline_guarded_fields(node)

            if inline_fields:
                nested_guarded_fields = set(guarded_fields)
                nested_guarded_fields.update(inline_fields)

                result = _classify_block(
                    node.body,
                    nested_guarded_fields,
                    False,
                    None,
                )
                if result[0] is not None:
                    return result

                result = _classify_block(
                    node.orelse,
                    nested_guarded_fields,
                    False,
                    None,
                )
                if result[0] is not None:
                    return result

            else:
                result = _classify_block(
                    node.body,
                    set(guarded_fields),
                    saw_callback,
                    callback_kind,
                )
                if result[0] is not None:
                    return result

                result = _classify_block(
                    node.orelse,
                    set(guarded_fields),
                    saw_callback,
                    callback_kind,
                )
                if result[0] is not None:
                    return result

            continue

        if isinstance(node, ast.Try):
            # The try body and each exception handler are separate paths.
            # A callback in the try body can invalidate the guarded field
            # before the else block executes on the successful path.
            result = _classify_block(
                node.body,
                set(guarded_fields),
                saw_callback,
                callback_kind,
            )
            if result[0] is not None:
                return result

            # Determine callback state produced by the try body so that
            # successful execution can carry it into the else block.
            try_callback_kinds: list[str] = []

            for statement in node.body:
                for expression in _statement_expressions(statement):
                    try_callback_kinds.extend(
                        _callback_calls_in_expression(expression)
                    )

            else_saw_callback = saw_callback
            else_callback_kind = callback_kind

            if try_callback_kinds:
                else_saw_callback = True
                else_callback_kind = try_callback_kinds[-1]

            result = _classify_block(
                node.orelse,
                set(guarded_fields),
                else_saw_callback,
                else_callback_kind,
            )
            if result[0] is not None:
                return result

            # Exception handlers execute only when the try body raises.
            # Analyze them independently so callback state from the
            # successful path does not leak into an unrelated handler.
            handler_callback_kinds: list[str] = []

            for handler in node.handlers:
                result = _classify_block(
                    handler.body,
                    set(guarded_fields),
                    saw_callback,
                    callback_kind,
                )
                if result[0] is not None:
                    return result

                for statement in handler.body:
                    for expression in _statement_expressions(statement):
                        handler_callback_kinds.extend(
                            _callback_calls_in_expression(expression)
                        )

            # finally executes after either the successful try/else path
            # or an exception-handler path. A callback on either path may
            # invalidate the guarded field before a finally dereference.
            finally_saw_callback = saw_callback
            finally_callback_kind = callback_kind

            if try_callback_kinds:
                finally_saw_callback = True
                finally_callback_kind = try_callback_kinds[-1]
            elif handler_callback_kinds:
                finally_saw_callback = True
                finally_callback_kind = handler_callback_kinds[-1]

            result = _classify_block(
                node.finalbody,
                set(guarded_fields),
                finally_saw_callback,
                finally_callback_kind,
            )
            if result[0] is not None:
                return result

            continue

        if isinstance(node, (ast.For, ast.AsyncFor, ast.While)):
            result = _classify_block(
                node.body,
                set(guarded_fields),
                saw_callback,
                callback_kind,
            )
            if result[0] is not None:
                return result

            result = _classify_block(
                node.orelse,
                set(guarded_fields),
                saw_callback,
                callback_kind,
            )
            if result[0] is not None:
                return result

            continue

        if isinstance(node, (ast.With, ast.AsyncWith)):
            result = _classify_block(
                node.body,
                set(guarded_fields),
                saw_callback,
                callback_kind,
            )
            if result[0] is not None:
                return result

            continue
        # An explicit assignment to a guarded self field invalidates the
        # invariant we are tracking. For example:
        #
        #     w_buffer = self.w_buffer
        #     self.w_buffer = None
        #     return w_buffer
        #
        # The final local-variable use is not a dereference of the guarded
        # self field, so the finding must be cleared here.
        if isinstance(node, ast.Assign):
            invalidated_fields: set[str] = set()

            for target in node.targets:
                field = _self_field(target)
                if field is not None:
                    invalidated_fields.add(field)

            if invalidated_fields:
                guarded_fields.difference_update(invalidated_fields)

                if not guarded_fields:
                    saw_callback = False
                    callback_kind = None
        expressions = _statement_expressions(node)

        if not expressions:
            continue

        # A guard in this statement establishes the invariant before
        # later statements. A guard in the same expression as the
        # dereference does not count as a re-check after a callback.
        statement_guarded_fields: set[str] = set()

        for expression in expressions:
            statement_guarded_fields.update(
                _guard_calls_in_expression(expression)
            )

        if statement_guarded_fields:
            guarded_fields = set(guarded_fields)
            guarded_fields.update(statement_guarded_fields)

            # A guard re-establishes the invariant and therefore
            # invalidates any callback state from before it.
            saw_callback = False
            callback_kind = None

        # If a callback has already happened, inspect the current
        # statement for the guarded-field dereference before treating
        # calls inside that statement as another callback.
        if saw_callback:
            for expression in expressions:
                # A simple assignment such as:
                #
                #     w_buffer = self.w_buffer
                #
                # merely copies the guarded field into a local variable.
                # It is intentionally not considered a dereference site.
                if (
                    isinstance(node, ast.Assign)
                    and isinstance(expression, ast.Attribute)
                    and _self_field(expression) in guarded_fields
                ):
                    continue

                if _contains_guarded_dereference(
                    expression,
                    guarded_fields,
                ):
                    return _callback_deref_reason(callback_kind)

        # Only after checking for the post-callback dereference do we
        # establish callback state for a callback statement.
        for expression in expressions:
            for kind in _callback_calls_in_expression(expression):
                # A call whose target is the guarded field is the
                # dereference itself, not the callback that creates the
                # TOCTOU window.
                if (
                    isinstance(expression, ast.Call)
                    and guarded_fields.intersection(
                        _dereferenced_fields(expression)
                    )
                ):
                    continue

                saw_callback = True
                callback_kind = kind

    return None, None


def _classify_guard_callback_deref(
    body: list[ast.stmt],
) -> tuple[str | None, str | None]:
    """Classify a guard -> callback -> dereference sequence."""
    return _classify_block(body, set())


def _is_app_exposed_method(
    node: ast.FunctionDef | ast.AsyncFunctionDef,
    tree: ast.Module,
) -> bool:
    """Return whether a method is exposed through interp2app."""
    for parent in ast.walk(tree):
        if not isinstance(parent, ast.Assign):
            continue

        for value in ast.walk(parent.value):
            if (
                isinstance(value, ast.Call)
                and isinstance(value.func, ast.Name)
                and value.func.id == "interp2app"
                and value.args
                and isinstance(value.args[0], ast.Attribute)
                and isinstance(value.args[0].value, ast.Name)
                and value.args[0].value.id == node.name
            ):
                return True

    for parent in ast.walk(tree):
        if not isinstance(parent, ast.Call):
            continue

        if (
            isinstance(parent.func, ast.Name)
            and parent.func.id == "interp2app"
            and parent.args
            and isinstance(parent.args[0], ast.Attribute)
            and parent.args[0].attr == node.name
        ):
            return True

    return False


def _scan_file(path: Path) -> tuple[int, list[dict[str, object]]]:
    """Scan one Python file for guard-callback-deref findings."""
    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (OSError, SyntaxError, UnicodeDecodeError):
        return 0, []

    functions_analyzed = 0
    findings: list[dict[str, object]] = []

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        if not _is_app_exposed_method(node, tree):
            continue

        functions_analyzed += 1

        classification, detail = _classify_guard_callback_deref(node.body)

        if classification is None:
            continue

        findings.append(
            {
                "classification": classification,
                "column": node.col_offset,
                "confidence": (
                    "high"
                    if "self-dispatch" in (detail or "")
                    else "medium"
                ),
                "detail": detail,
                "file": str(path),
                "function": node.name,
                "line": node.lineno,
                "message": (
                    f"{node.name}() has a guard -> app-level callback -> "
                    "guarded-field dereference sequence"
                ),
                "type": "guard-callback-deref",
            }
        )

    return functions_analyzed, findings


def _scan_tree(root: Path) -> dict[str, object]:
    """Scan a PyPy checkout and return JSON-serializable results."""
    pypy_root = root / "pypy"

    if not pypy_root.is_dir():
        raise SystemExit(f"not a PyPy checkout: {root}")

    functions_analyzed = 0
    findings: list[dict[str, object]] = []

    for path in sorted(pypy_root.rglob("*.py")):
        analyzed, file_findings = _scan_file(path)
        functions_analyzed += analyzed
        findings.extend(file_findings)

    by_classification: dict[str, int] = {}

    for finding in findings:
        classification = str(finding["classification"])
        by_classification[classification] = (
            by_classification.get(classification, 0) + 1
        )

    return {
        "functions_analyzed": functions_analyzed,
        "findings": findings,
        "summary": {
            "by_classification": by_classification,
            "total_findings": len(findings),
        },
    }


def main() -> int:
    """Run the scanner from the command line."""
    import json
    import sys

    if len(sys.argv) != 2:
        print(
            "usage: python scan_guard_callback_deref.py <pypy-root>",
            file=sys.stderr,
        )
        return 2

    results = _scan_tree(Path(sys.argv[1]))
    print(json.dumps(results, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())