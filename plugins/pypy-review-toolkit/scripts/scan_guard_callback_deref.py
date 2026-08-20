"""Detect guard -> app-level callback -> guarded-field dereference patterns."""

from __future__ import annotations

import ast
from pathlib import Path


def _attribute_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Attribute):
        return node.attr
    return None


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

    if not func.attr.startswith("_check_"):
        return set()

    # The common PyPy guard form is self._check_attached(space), where
    # the guard establishes the object's attached/buffer invariant.
    #
    # Keep this deliberately conservative: infer the field only from
    # the known guard name rather than treating every _check_* call as
    # a guard for every self field.
    if func.attr == "_check_attached":
        return {"w_buffer"}

    return set()


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
        if node.args and isinstance(node.args[0], ast.Name):
            if node.args[0].id == "self":
                return "self-dispatch"

        if node.args and isinstance(node.args[0], ast.Attribute):
            if (
                isinstance(node.args[0].value, ast.Name)
                and node.args[0].value.id == "self"
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
    """Return self fields used as objects/values after a callback."""
    fields: set[str] = set()

    if isinstance(node, ast.Attribute):
        field = _self_field(node)
        if field is not None:
            fields.add(field)

    if isinstance(node, ast.Call):
        for arg in node.args:
            fields.update(_dereferenced_fields(arg))

        for keyword in node.keywords:
            fields.update(_dereferenced_fields(keyword.value))

    if isinstance(node, ast.Return) and node.value is not None:
        fields.update(_dereferenced_fields(node.value))

    return fields


def _classify_guard_callback_deref(
    body: list[ast.stmt],
) -> tuple[str | None, str | None]:
    """Classify a guard -> callback -> dereference sequence."""
    guarded_fields: set[str] = set()
    saw_callback = False
    callback_kind: str | None = None

    for node in body:
        if isinstance(node, ast.Call):
            guard_fields = _guarded_fields_from_call(node)
            if guard_fields:
                guarded_fields.update(guard_fields)
                saw_callback = False
                callback_kind = None
                continue

            kind = _callback_kind(node)
            if kind is not None:
                saw_callback = True
                callback_kind = kind
                continue

            if saw_callback:
                dereferenced = _dereferenced_fields(node)
                if guarded_fields.intersection(dereferenced):
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

        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call):
            call = node.value

            guard_fields = _guarded_fields_from_call(call)
            if guard_fields:
                guarded_fields.update(guard_fields)
                saw_callback = False
                callback_kind = None
                continue

            kind = _callback_kind(call)
            if kind is not None:
                saw_callback = True
                callback_kind = kind
                continue

        elif isinstance(node, ast.Return):
            if node.value is None or not saw_callback:
                continue

            dereferenced = _dereferenced_fields(node.value)
            if guarded_fields.intersection(dereferenced):
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

        elif isinstance(node, ast.If):
            inline_fields = _inline_guarded_fields(node)
            if inline_fields:
                guarded_fields.update(inline_fields)
                saw_callback = False
                callback_kind = None

    return None, None


def _find_exposed_methods(tree: ast.Module) -> set[tuple[str, str]]:
    """Find methods registered through interp2app(ClassName.method)."""
    exposed: set[tuple[str, str]] = set()

    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "interp2app"
            and node.args
            and isinstance(node.args[0], ast.Attribute)
        ):
            attr = node.args[0]

            if isinstance(attr.value, ast.Name):
                exposed.add((attr.value.id, attr.attr))

    return exposed


def _finding(
    path: Path,
    project_root: Path,
    class_name: str,
    method: ast.FunctionDef,
    classification: str,
    reason: str,
) -> dict:
    try:
        relative_path = str(path.relative_to(project_root))
    except ValueError:
        relative_path = str(path)

    return {
        "type": "guard-callback-deref",
        "classification": classification,
        "confidence": "high",
        "file": relative_path,
        "line": method.lineno,
        "column": method.col_offset,
        "function": method.name,
        "message": (
            f"{class_name}.{method.name}() has a guard -> app-level "
            "callback -> guarded-field dereference sequence"
        ),
        "detail": reason,
    }


def _scan_file(path: Path, project_root: Path) -> list[dict]:
    """Scan one Python file for exposed methods with the bug shape."""
    try:
        source = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return []

    try:
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    exposed = _find_exposed_methods(tree)

    if not exposed:
        return []

    findings: list[dict] = []

    for node in tree.body:
        if not isinstance(node, ast.ClassDef):
            continue

        class_methods = {
            method.name: method
            for method in node.body
            if isinstance(method, ast.FunctionDef)
        }

        for class_name, method_name in exposed:
            if class_name != node.name:
                continue

            method = class_methods.get(method_name)
            if method is None:
                continue

            classification, reason = _classify_guard_callback_deref(
                method.body
            )

            if classification is None:
                continue

            findings.append(
                _finding(
                    path,
                    project_root,
                    class_name,
                    method,
                    classification,
                    reason or "",
                )
            )

    return findings


def _iter_python_files(root: Path) -> list[Path]:
    """Return Python source files under a PyPy checkout."""
    files: list[Path] = []

    for path in root.rglob("*.py"):
        parts = set(path.parts)

        if "test" in parts or "tests" in parts:
            continue

        if ".git" in parts:
            continue

        files.append(path)

    return sorted(files)


def analyze(root: str) -> dict:
    """Scan a PyPy checkout and return JSON-serializable results."""
    project_root = Path(root).resolve()

    if not project_root.is_dir():
        raise SystemExit(f"PyPy checkout does not exist: {project_root}")

    files = _iter_python_files(project_root)
    findings: list[dict] = []

    for path in files:
        findings.extend(_scan_file(path, project_root))

    by_classification: dict[str, int] = {}

    for finding in findings:
        classification = finding["classification"]
        by_classification[classification] = (
            by_classification.get(classification, 0) + 1
        )

    return {
        "scanner": "guard-callback-deref",
        "root": str(project_root),
        "functions_analyzed": len(files),
        "findings": findings,
        "summary": {
            "total_findings": len(findings),
            "by_classification": by_classification,
        },
    }


def main() -> None:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        description=(
            "Detect guard -> app-level callback -> guarded-field "
            "dereference patterns in a PyPy checkout."
        )
    )
    parser.add_argument(
        "root",
        help="path to the PyPy checkout",
    )
    args = parser.parse_args()

    result = analyze(args.root)
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
