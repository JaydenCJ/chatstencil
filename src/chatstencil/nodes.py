"""AST node types produced by the parser and consumed by the evaluator.

Nodes are deliberately dumb containers: all behavior lives in
:mod:`chatstencil.evaluate` so the tree stays trivially inspectable in tests.
Every node records the 1-based source line it started on for error messages.
"""

from __future__ import annotations

from typing import Any, List, Optional, Sequence, Tuple


class Node:
    __slots__ = ("line",)

    def __init__(self, line: int):
        self.line = line


# --------------------------------------------------------------------------
# Statements
# --------------------------------------------------------------------------


class Text(Node):
    """Literal template text, emitted byte-for-byte."""

    __slots__ = ("text",)

    def __init__(self, text: str, line: int):
        super().__init__(line)
        self.text = text


class Output(Node):
    """``{{ expression }}``"""

    __slots__ = ("expr",)

    def __init__(self, expr: "Node", line: int):
        super().__init__(line)
        self.expr = expr


class For(Node):
    """``{% for target in iterable %} body {% endfor %}``"""

    __slots__ = ("target", "iterable", "body")

    def __init__(self, target: str, iterable: "Node", body: List[Node], line: int):
        super().__init__(line)
        self.target = target
        self.iterable = iterable
        self.body = body


class If(Node):
    """``{% if %}/{% elif %}/{% else %}`` as (condition, body) branches.

    The final ``else`` branch, when present, has a condition of ``None``.
    """

    __slots__ = ("branches",)

    def __init__(self, branches: List[Tuple[Optional[Node], List[Node]]], line: int):
        super().__init__(line)
        self.branches = branches


class SetStmt(Node):
    """``{% set name = expr %}`` or ``{% set ns.attr = expr %}``"""

    __slots__ = ("name", "attr", "expr")

    def __init__(self, name: str, attr: Optional[str], expr: Node, line: int):
        super().__init__(line)
        self.name = name
        self.attr = attr
        self.expr = expr


# --------------------------------------------------------------------------
# Expressions
# --------------------------------------------------------------------------


class Literal(Node):
    __slots__ = ("value",)

    def __init__(self, value: Any, line: int):
        super().__init__(line)
        self.value = value


class Name(Node):
    __slots__ = ("name",)

    def __init__(self, name: str, line: int):
        super().__init__(line)
        self.name = name


class ListLit(Node):
    __slots__ = ("items",)

    def __init__(self, items: Sequence[Node], line: int):
        super().__init__(line)
        self.items = list(items)


class GetAttr(Node):
    """``obj.name`` — mapping key lookup, namespace attribute, or method ref."""

    __slots__ = ("obj", "name")

    def __init__(self, obj: Node, name: str, line: int):
        super().__init__(line)
        self.obj = obj
        self.name = name


class GetItem(Node):
    """``obj[key]``"""

    __slots__ = ("obj", "key")

    def __init__(self, obj: Node, key: Node, line: int):
        super().__init__(line)
        self.obj = obj
        self.key = key


class Call(Node):
    """A call: global function (``func`` is Name) or method (``func`` is GetAttr)."""

    __slots__ = ("func", "args", "kwargs")

    def __init__(
        self,
        func: Node,
        args: Sequence[Node],
        kwargs: Sequence[Tuple[str, Node]],
        line: int,
    ):
        super().__init__(line)
        self.func = func
        self.args = list(args)
        self.kwargs = list(kwargs)


class Filter(Node):
    """``value | name`` or ``value | name(arg, ...)``"""

    __slots__ = ("node", "name", "args")

    def __init__(self, node: Node, name: str, args: Sequence[Node], line: int):
        super().__init__(line)
        self.node = node
        self.name = name
        self.args = list(args)


class Test(Node):
    """``value is name`` / ``value is not name``"""

    __slots__ = ("node", "name", "negated")

    def __init__(self, node: Node, name: str, negated: bool, line: int):
        super().__init__(line)
        self.node = node
        self.name = name
        self.negated = negated


class BinOp(Node):
    """Binary operator; ``op`` is one of the parser's operator strings."""

    __slots__ = ("op", "left", "right")

    def __init__(self, op: str, left: Node, right: Node, line: int):
        super().__init__(line)
        self.op = op
        self.left = left
        self.right = right


class UnaryOp(Node):
    """``not x`` or ``-x``; ``op`` is ``"not"`` or ``"neg"``."""

    __slots__ = ("op", "operand")

    def __init__(self, op: str, operand: Node, line: int):
        super().__init__(line)
        self.op = op
        self.operand = operand


class CondExpr(Node):
    """Inline conditional: ``a if cond else b`` (``else`` optional)."""

    __slots__ = ("test", "true", "false")

    def __init__(self, test: Node, true: Node, false: Optional[Node], line: int):
        super().__init__(line)
        self.test = test
        self.true = true
        self.false = false
