"""Built-in template filters.

The set is the intersection of "what Jinja provides" and "what published chat
templates actually use", implemented on the standard library alone.  Filters
are plain functions ``f(value, *args)``; unknown filters are rejected at
render time by the evaluator with the list of supported names.
"""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, Sequence

from .errors import TemplateRuntimeError
from .runtime import Undefined, is_undefined, to_text


def _require_defined(value: Any, filter_name: str) -> Any:
    if is_undefined(value):
        raise TemplateRuntimeError(
            f"filter '{filter_name}' applied to an undefined value"
        )
    return value


def _as_sequence(value: Any, filter_name: str) -> Sequence[Any]:
    _require_defined(value, filter_name)
    if isinstance(value, (list, tuple, str)):
        return value
    raise TemplateRuntimeError(
        f"filter '{filter_name}' expects a sequence, got {type(value).__name__}"
    )


def _trim(value: Any, chars: Any = None) -> str:
    return to_text(value).strip(chars)


def _length(value: Any) -> int:
    value = _require_defined(value, "length")
    try:
        return len(value)
    except TypeError:
        raise TemplateRuntimeError(
            f"object of type {type(value).__name__} has no length"
        ) from None


def _first(value: Any) -> Any:
    seq = _as_sequence(value, "first")
    if not seq:
        raise TemplateRuntimeError("filter 'first' applied to an empty sequence")
    return seq[0]


def _last(value: Any) -> Any:
    seq = _as_sequence(value, "last")
    if not seq:
        raise TemplateRuntimeError("filter 'last' applied to an empty sequence")
    return seq[-1]


def _join(value: Any, sep: str = "") -> str:
    seq = _as_sequence(value, "join")
    return sep.join(to_text(item) for item in seq)


def _replace(value: Any, old: str, new: str, count: int = -1) -> str:
    return to_text(_require_defined(value, "replace")).replace(old, new, count)


def _default(value: Any, fallback: Any = "", boolean: Any = False) -> Any:
    """Jinja's ``default``: fallback for undefined (or falsy, if boolean=true)."""
    if is_undefined(value):
        return fallback
    if boolean and not value:
        return fallback
    return value


def _int(value: Any, fallback: int = 0) -> int:
    try:
        if isinstance(value, str):
            return int(value.strip(), 10)
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return int(value)
        if isinstance(value, bool):
            return int(value)
    except ValueError:
        pass
    return fallback


def _float(value: Any, fallback: float = 0.0) -> float:
    try:
        if isinstance(value, (str, int, float)):
            return float(value)
    except ValueError:
        pass
    return fallback


def _list(value: Any) -> list:
    value = _require_defined(value, "list")
    if isinstance(value, dict):
        return list(value.keys())
    try:
        return list(value)
    except TypeError:
        raise TemplateRuntimeError(
            f"filter 'list' cannot iterate {type(value).__name__}"
        ) from None


def _reverse(value: Any) -> Any:
    seq = _as_sequence(value, "reverse")
    if isinstance(seq, str):
        return seq[::-1]
    return list(reversed(seq))


def _tojson(value: Any, indent: Any = None) -> str:
    value = _require_defined(value, "tojson")
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True, indent=indent)
    except TypeError:
        raise TemplateRuntimeError(
            f"filter 'tojson' cannot serialize {type(value).__name__}"
        ) from None


def _indent(value: Any, width: int = 4, first: bool = False) -> str:
    """Indent every line after the first by *width* spaces (Jinja semantics)."""
    pad = " " * width
    lines = to_text(value).split("\n")
    head = (pad + lines[0]) if first else lines[0]
    return "\n".join([head] + [pad + line if line else line for line in lines[1:]])


def _abs(value: Any) -> Any:
    value = _require_defined(value, "abs")
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TemplateRuntimeError("filter 'abs' expects a number")
    return abs(value)


FILTERS: Dict[str, Callable[..., Any]] = {
    "trim": _trim,
    "upper": lambda v: to_text(_require_defined(v, "upper")).upper(),
    "lower": lambda v: to_text(_require_defined(v, "lower")).lower(),
    "title": lambda v: to_text(_require_defined(v, "title")).title(),
    "capitalize": lambda v: to_text(_require_defined(v, "capitalize")).capitalize(),
    "length": _length,
    "count": _length,  # Jinja alias
    "first": _first,
    "last": _last,
    "join": _join,
    "replace": _replace,
    "default": _default,
    "d": _default,  # Jinja alias
    "string": lambda v: to_text(v),
    "int": _int,
    "float": _float,
    "list": _list,
    "reverse": _reverse,
    "tojson": _tojson,
    "indent": _indent,
    "abs": _abs,
    # Chat templates targeting HTML-escaping engines mark segments `| safe`;
    # chatstencil never escapes, so it is the identity.
    "safe": lambda v: v,
}


def apply_filter(name: str, value: Any, args: Sequence[Any]) -> Any:
    func = FILTERS.get(name)
    if func is None:
        supported = ", ".join(sorted(FILTERS))
        raise TemplateRuntimeError(
            f"unknown filter '{name}' (supported: {supported})"
        )
    try:
        return func(value, *args)
    except TemplateRuntimeError:
        raise
    except TypeError as exc:
        raise TemplateRuntimeError(f"filter '{name}': {exc}") from None


# Re-exported for the evaluator's `default`-style shortcuts.
__all__ = ["FILTERS", "apply_filter", "Undefined"]
