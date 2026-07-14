"""Runtime value types shared by the evaluator and the filter library.

Contains the :class:`Undefined` placeholder (Jinja-compatible semantics: falsy,
renders as the empty string, equal only to other undefineds), the
:class:`Namespace` object backing the template-level ``namespace()`` helper,
and the canonical value → text conversion used for output, ``~`` concatenation
and the ``string`` filter.
"""

from __future__ import annotations

from typing import Any

from .errors import TemplateRuntimeError


class Undefined:
    """Placeholder for a missing variable, attribute, or index.

    Mirrors the parts of Jinja's default ``Undefined`` that chat templates
    rely on: it is falsy, compares equal only to other undefined values,
    renders as ``""``, and fails loudly (with the missing name) when iterated.
    """

    __slots__ = ("_name",)

    def __init__(self, name: str = "value"):
        self._name = name

    def __bool__(self) -> bool:
        return False

    def __str__(self) -> str:
        return ""

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Undefined({self._name!r})"

    def __eq__(self, other: Any) -> bool:
        return isinstance(other, Undefined)

    def __ne__(self, other: Any) -> bool:
        return not isinstance(other, Undefined)

    def __hash__(self) -> int:
        return hash(Undefined)

    def __iter__(self):
        raise TemplateRuntimeError(f"'{self._name}' is undefined")

    def __len__(self) -> int:
        raise TemplateRuntimeError(f"'{self._name}' is undefined")

    def __contains__(self, item: Any) -> bool:
        raise TemplateRuntimeError(f"'{self._name}' is undefined")


class Namespace:
    """Attribute bag created by ``namespace(...)`` in a template.

    Exists for the same reason as in Jinja: ``{% set %}`` inside a loop writes
    to the loop scope, so templates that accumulate state across iterations
    (e.g. "was there a system message?") need a mutable object instead.
    """

    def __init__(self, **attrs: Any):
        self.__dict__.update(attrs)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        inner = ", ".join(f"{k}={v!r}" for k, v in sorted(self.__dict__.items()))
        return f"namespace({inner})"


def is_undefined(value: Any) -> bool:
    return isinstance(value, Undefined)


def to_text(value: Any) -> str:
    """Convert a template value to output text, matching Jinja.

    ``Undefined`` renders as the empty string; ``None`` and booleans render
    as their Python names (``None``, ``True``, ``False``) — Jinja does the
    same, and prompt strings must not paper over that kind of bug.
    """
    if isinstance(value, Undefined):
        return ""
    if isinstance(value, str):
        return value
    return str(value)
