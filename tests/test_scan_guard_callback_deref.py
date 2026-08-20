import ast
import importlib.util
import textwrap
from pathlib import Path


SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "plugins"
    / "pypy-review-toolkit"
    / "scripts"
    / "scan_guard_callback_deref.py"
)

SPEC = importlib.util.spec_from_file_location(
    "scan_guard_callback_deref",
    SCRIPT,
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)

_classify_guard_callback_deref = MODULE._classify_guard_callback_deref


def _body(source):
    return ast.parse(textwrap.dedent(source)).body


def test_guard_callback_then_deref_is_consider():
    body = _body(
        """
        self._check_attached(space)
        space.call_method(self, "flush")
        return space.call_method(self.w_buffer, "close")
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification == "CONSIDER"
    assert "guard-callback-deref" in reason


def test_guard_callback_then_attribute_use_is_consider():
    body = _body(
        """
        self._check_attached(space)
        space.call_method(self, "flush")
        return self.w_buffer
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification == "CONSIDER"
    assert "guard-callback-deref" in reason


def test_recheck_after_callback_clears_finding():
    body = _body(
        """
        self._check_attached(space)
        space.call_method(self, "flush")
        self._check_attached(space)
        return space.call_method(self.w_buffer, "close")
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification is None
    assert reason is None


def test_callback_without_guard_is_not_this_class():
    body = _body(
        """
        space.call_method(self, "flush")
        return space.call_method(self.w_buffer, "close")
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification is None
    assert reason is None


def test_guard_without_callback_is_not_this_class():
    body = _body(
        """
        self._check_attached(space)
        return space.call_method(self.w_buffer, "close")
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification is None
    assert reason is None


def test_self_dispatch_is_high_signal():
    body = _body(
        """
        self._check_attached(space)
        space.call_method(self, "flush")
        return space.call_method(self.w_buffer, "truncate")
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification == "CONSIDER"
    assert "self-dispatch" in reason


def test_internal_object_dispatch_is_lower_signal():
    body = _body(
        """
        self._check_attached(space)
        space.call_method(self.w_decoder, "reset")
        return space.call_method(self.w_buffer, "truncate")
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification == "CONSIDER"
    assert "guard-callback-deref" in reason


def test_callback_does_not_count_as_guard():
    body = _body(
        """
        space.call_method(self, "flush")
        return space.call_method(self.w_buffer, "close")
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification is None
    assert reason is None


def test_detach_pattern_is_not_automatically_reported():
    body = _body(
        """
        self._check_attached(space)
        space.call_method(self, "flush")
        w_buffer = self.w_buffer
        self.w_buffer = None
        return w_buffer
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification is None
    assert reason is None


def test_textio_truncate_issue_10_pattern_is_consider():
    body = _body(
        """
        self._check_attached(space)
        space.call_method(self, "flush")
        return space.call_method(self.w_buffer, "truncate", w_pos)
        """
    )

    classification, reason = _classify_guard_callback_deref(body)

    assert classification == "CONSIDER"
    assert "self-dispatch" in reason
    assert "guard-callback-deref" in reason
