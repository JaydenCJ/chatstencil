"""Tree-walking evaluator for compiled templates.

Design points:

- **Sandboxed by construction.** There is no attribute access on arbitrary
  Python objects: ``obj.name`` resolves mapping keys, namespace attributes,
  or an explicit allowlist of methods per built-in type. Nothing else is
  reachable, so untrusted template files cannot escape into the interpreter.
- **Jinja-faithful where it matters.** ``{% set %}`` writes to the innermost
  scope (so loop bodies do not leak — the reason ``namespace()`` exists),
  missing keys and out-of-range indexes yield :class:`Undefined`, and
  ``loop.first/last/index0`` behave exactly as chat templates expect.
- **Loud errors.** Every runtime failure carries the template name and line.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from . import nodes
from .errors import TemplateRuntimeError
from .filters import apply_filter
from .runtime import Namespace, Undefined, is_undefined, to_text

# Methods callable from templates, per receiver type.  This is the entire
# attack surface for method calls; anything else raises a clear error.
_ALLOWED_METHODS: Dict[type, frozenset] = {
    str: frozenset(
        (
            "strip",
            "lstrip",
            "rstrip",
            "upper",
            "lower",
            "title",
            "capitalize",
            "startswith",
            "endswith",
            "replace",
            "split",
            "find",
            "join",
            "removeprefix",
            "removesuffix",
        )
    ),
    dict: frozenset(("get", "keys", "values", "items")),
    list: frozenset(("index", "count")),
}

_TESTS = {
    "defined": lambda v: not is_undefined(v),
    "undefined": is_undefined,
    "none": lambda v: v is None,
    "string": lambda v: isinstance(v, str),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "mapping": lambda v: isinstance(v, dict),
    "sequence": lambda v: isinstance(v, (list, tuple, str)),
    "iterable": lambda v: isinstance(v, (list, tuple, str, dict)),
    "odd": lambda v: isinstance(v, int) and not isinstance(v, bool) and v % 2 == 1,
    "even": lambda v: isinstance(v, int) and not isinstance(v, bool) and v % 2 == 0,
}

_MAX_RANGE = 10_000  # cap template-created ranges; prompts are not that long


class Evaluator:
    """Renders a parsed template body against a variable context."""

    def __init__(self, name: str, variables: Dict[str, Any]):
        self.name = name
        # A stack of scopes; lookups walk outward, `set` writes innermost.
        self.scopes: List[Dict[str, Any]] = [dict(variables)]

    # -- public entry point --------------------------------------------------

    def render(self, body: List[nodes.Node]) -> str:
        parts: List[str] = []
        self._exec_body(body, parts)
        return "".join(parts)

    # -- helpers ------------------------------------------------------

    def _fail(self, message: str, node: nodes.Node) -> "TemplateRuntimeError":
        raise TemplateRuntimeError(message, self.name, node.line)

    def _lookup(self, name: str) -> Any:
        for scope in reversed(self.scopes):
            if name in scope:
                return scope[name]
        return Undefined(name)

    # -- statements ------------------------------------------------------

    def _exec_body(self, body: List[nodes.Node], parts: List[str]) -> None:
        for node in body:
            if isinstance(node, nodes.Text):
                parts.append(node.text)
            elif isinstance(node, nodes.Output):
                parts.append(to_text(self._eval(node.expr)))
            elif isinstance(node, nodes.If):
                self._exec_if(node, parts)
            elif isinstance(node, nodes.For):
                self._exec_for(node, parts)
            elif isinstance(node, nodes.SetStmt):
                self._exec_set(node)
            else:  # pragma: no cover - parser only emits the above
                self._fail(f"unsupported node {type(node).__name__}", node)

    def _exec_if(self, node: nodes.If, parts: List[str]) -> None:
        for condition, body in node.branches:
            if condition is None or self._truth(self._eval(condition)):
                self._exec_body(body, parts)
                return

    def _exec_for(self, node: nodes.For, parts: List[str]) -> None:
        iterable = self._eval(node.iterable)
        if is_undefined(iterable):
            self._fail(f"cannot iterate undefined value in 'for {node.target}'", node)
        if isinstance(iterable, dict):
            items = list(iterable.keys())
        elif isinstance(iterable, (list, tuple, str, range)):
            items = list(iterable)
        else:
            self._fail(
                f"'for' expects a sequence or mapping, got {type(iterable).__name__}",
                node,
            )
        length = len(items)
        scope: Dict[str, Any] = {}
        self.scopes.append(scope)
        try:
            for index, item in enumerate(items):
                scope.clear()
                scope[node.target] = item
                scope["loop"] = {
                    "index": index + 1,
                    "index0": index,
                    "first": index == 0,
                    "last": index == length - 1,
                    "length": length,
                    "revindex": length - index,
                    "revindex0": length - index - 1,
                }
                self._exec_body(node.body, parts)
        finally:
            self.scopes.pop()

    def _exec_set(self, node: nodes.SetStmt) -> None:
        value = self._eval(node.expr)
        if node.attr is None:
            self.scopes[-1][node.name] = value
            return
        target = self._lookup(node.name)
        if not isinstance(target, Namespace):
            kind = "undefined" if is_undefined(target) else type(target).__name__
            self._fail(
                f"'{node.name}.{node.attr} = ...' needs a namespace() object, "
                f"got {kind}",
                node,
            )
        setattr(target, node.attr, value)

    # -- expressions ------------------------------------------------------

    def _eval(self, node: nodes.Node) -> Any:
        method = getattr(self, "_eval_" + type(node).__name__.lower(), None)
        if method is None:  # pragma: no cover - parser only emits known nodes
            self._fail(f"unsupported expression {type(node).__name__}", node)
        return method(node)

    def _eval_literal(self, node: nodes.Literal) -> Any:
        return node.value

    def _eval_name(self, node: nodes.Name) -> Any:
        return self._lookup(node.name)

    def _eval_listlit(self, node: nodes.ListLit) -> list:
        return [self._eval(item) for item in node.items]

    def _eval_getattr(self, node: nodes.GetAttr) -> Any:
        obj = self._eval(node.obj)
        if is_undefined(obj):
            self._fail(f"cannot read '.{node.name}' of undefined value", node)
        if isinstance(obj, dict):
            if node.name in obj:
                return obj[node.name]
            return Undefined(node.name)
        if isinstance(obj, Namespace):
            try:
                return getattr(obj, node.name)
            except AttributeError:
                return Undefined(node.name)
        # For plain values, bare attribute access (not a call) has no meaning
        # in the sandbox; report missing rather than exposing Python internals.
        return Undefined(node.name)

    def _eval_getitem(self, node: nodes.GetItem) -> Any:
        obj = self._eval(node.obj)
        key = self._eval(node.key)
        if is_undefined(obj):
            self._fail("cannot index an undefined value", node)
        try:
            return obj[key]
        except (KeyError, IndexError):
            # Jinja resolves failed subscripts to undefined; templates rely on
            # patterns like `messages[0] is defined`.
            return Undefined(f"[{key!r}]")
        except TypeError:
            self._fail(
                f"{type(obj).__name__} is not indexable with {type(key).__name__}",
                node,
            )

    def _eval_call(self, node: nodes.Call) -> Any:
        args = [self._eval(a) for a in node.args]
        kwargs = {k: self._eval(v) for k, v in node.kwargs}
        if isinstance(node.func, nodes.Name):
            return self._call_global(node.func.name, args, kwargs, node)
        if isinstance(node.func, nodes.GetAttr):
            return self._call_method(node.func, args, kwargs, node)
        self._fail("only names and methods are callable", node)

    def _call_global(
        self, name: str, args: list, kwargs: dict, node: nodes.Call
    ) -> Any:
        if name == "raise_exception":
            message = to_text(args[0]) if args else "raise_exception()"
            self._fail(f"template raised: {message}", node)
        if name == "namespace":
            if args:
                self._fail("namespace() accepts keyword arguments only", node)
            return Namespace(**kwargs)
        if name == "range":
            if kwargs or not 1 <= len(args) <= 3:
                self._fail("range() takes 1 to 3 positional arguments", node)
            if not all(isinstance(a, int) and not isinstance(a, bool) for a in args):
                self._fail("range() arguments must be integers", node)
            r = range(*args)
            if len(r) > _MAX_RANGE:
                self._fail(f"range() longer than {_MAX_RANGE} is not allowed", node)
            return list(r)
        self._fail(
            f"'{name}' is not callable "
            "(available: namespace, raise_exception, range)",
            node,
        )

    def _call_method(
        self, func: nodes.GetAttr, args: list, kwargs: dict, node: nodes.Call
    ) -> Any:
        obj = self._eval(func.obj)
        if is_undefined(obj):
            self._fail(f"cannot call '.{func.name}()' on undefined value", node)
        if kwargs:
            self._fail("method calls do not accept keyword arguments", node)
        # Mapping keys shadow methods, matching GetAttr resolution order.
        if isinstance(obj, dict) and func.name in obj:
            self._fail(f"dict value '{func.name}' is not callable", node)
        allowed = _ALLOWED_METHODS.get(type(obj), frozenset())
        if func.name not in allowed:
            self._fail(
                f"method '.{func.name}()' is not allowed on "
                f"{type(obj).__name__} (allowed: "
                f"{', '.join(sorted(allowed)) or 'none'})",
                node,
            )
        try:
            return getattr(obj, func.name)(*args)
        except (TypeError, ValueError) as exc:
            self._fail(f".{func.name}(): {exc}", node)

    def _eval_filter(self, node: nodes.Filter) -> Any:
        value = self._eval(node.node)
        args = [self._eval(a) for a in node.args]
        try:
            return apply_filter(node.name, value, args)
        except TemplateRuntimeError as exc:
            raise TemplateRuntimeError(exc.message, self.name, node.line) from None

    def _eval_test(self, node: nodes.Test) -> bool:
        func = _TESTS.get(node.name)
        if func is None:
            supported = ", ".join(sorted(_TESTS))
            self._fail(f"unknown test '{node.name}' (supported: {supported})", node)
        result = func(self._eval(node.node))
        return (not result) if node.negated else result

    def _eval_binop(self, node: nodes.BinOp) -> Any:
        op = node.op
        if op == "and":
            left = self._eval(node.left)
            return self._eval(node.right) if self._truth(left) else left
        if op == "or":
            left = self._eval(node.left)
            return left if self._truth(left) else self._eval(node.right)
        left = self._eval(node.left)
        right = self._eval(node.right)
        if op == "~":
            return to_text(left) + to_text(right)
        if op in ("==", "!="):
            equal = left == right
            return equal if op == "==" else not equal
        if op in ("in", "not in"):
            if is_undefined(right):
                self._fail("'in' against an undefined value", node)
            try:
                contained = left in right
            except TypeError:
                self._fail(
                    f"'in' not supported for {type(right).__name__}", node
                )
            return contained if op == "in" else not contained
        if is_undefined(left) or is_undefined(right):
            self._fail(f"'{op}' with an undefined operand", node)
        try:
            if op == "+":
                return left + right
            if op == "-":
                return left - right
            if op == "*":
                return left * right
            if op == "/":
                return left / right
            if op == "%":
                return left % right
            if op == "<":
                return left < right
            if op == "<=":
                return left <= right
            if op == ">":
                return left > right
            if op == ">=":
                return left >= right
        except TypeError:
            self._fail(
                f"unsupported operand types for '{op}': "
                f"{type(left).__name__} and {type(right).__name__}",
                node,
            )
        except ZeroDivisionError:
            self._fail("division by zero", node)
        self._fail(f"unknown operator '{op}'", node)  # pragma: no cover

    def _eval_unaryop(self, node: nodes.UnaryOp) -> Any:
        value = self._eval(node.operand)
        if node.op == "not":
            return not self._truth(value)
        # neg
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            self._fail("unary '-' expects a number", node)
        return -value

    def _eval_condexpr(self, node: nodes.CondExpr) -> Any:
        if self._truth(self._eval(node.test)):
            return self._eval(node.true)
        if node.false is None:
            return Undefined("inline-if without else")
        return self._eval(node.false)

    @staticmethod
    def _truth(value: Any) -> bool:
        return bool(value)
