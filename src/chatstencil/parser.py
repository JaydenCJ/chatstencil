"""Recursive-descent parser for the chatstencil template dialect.

Grammar (statements)::

    template  : (text | output | block)*
    output    : '{{' expression '}}'
    block     : for | if | set
    for       : '{% for' NAME 'in' expression '%}' template '{% endfor %}'
    if        : '{% if' expr '%}' template
                ('{% elif' expr '%}' template)*
                ('{% else %}' template)? '{% endif %}'
    set       : '{% set' NAME ('.' NAME)? '=' expression '%}'

Expression precedence, loosest to tightest (mirrors Jinja)::

    ternary  →  or  →  and  →  not  →  comparison / in / is  →
    ~ (concat)  →  + -  →  * / %  →  unary -  →
    postfix (.attr  [item]  (call)  |filter)  →  primary
"""

from __future__ import annotations

from typing import List, Optional, Tuple

from . import nodes
from .errors import TemplateSyntaxError
from .lexer import (
    TOKEN_BLOCK_BEGIN,
    TOKEN_BLOCK_END,
    TOKEN_EOF,
    TOKEN_NAME,
    TOKEN_NUMBER,
    TOKEN_OP,
    TOKEN_STRING,
    TOKEN_TEXT,
    TOKEN_VAR_BEGIN,
    TOKEN_VAR_END,
    Token,
)

_COMPARE_OPS = frozenset(("==", "!=", "<", "<=", ">", ">="))
_STATEMENT_KEYWORDS = frozenset(("for", "if", "set"))
_END_KEYWORDS = frozenset(("endfor", "elif", "else", "endif"))


class Parser:
    def __init__(self, tokens: List[Token], name: str = "<template>"):
        self.tokens = tokens
        self.pos = 0
        self.name = name

    # -- token plumbing ------------------------------------------------------

    def _peek(self, offset: int = 0) -> Token:
        i = min(self.pos + offset, len(self.tokens) - 1)
        return self.tokens[i]

    def _next(self) -> Token:
        tok = self.tokens[self.pos]
        if tok.kind != TOKEN_EOF:
            self.pos += 1
        return tok

    def _fail(self, message: str, tok: Optional[Token] = None) -> "TemplateSyntaxError":
        tok = tok or self._peek()
        raise TemplateSyntaxError(message, self.name, tok.line)

    def _expect(self, kind: str, value: Optional[str] = None) -> Token:
        tok = self._next()
        if tok.kind != kind or (value is not None and tok.value != value):
            want = value if value is not None else kind
            got = tok.value if tok.value else tok.kind
            self._fail(f"expected {want!r}, got {got!r}", tok)
        return tok

    def _at_op(self, *values: str) -> bool:
        tok = self._peek()
        return tok.kind == TOKEN_OP and tok.value in values

    def _at_name(self, *values: str) -> bool:
        tok = self._peek()
        return tok.kind == TOKEN_NAME and tok.value in values

    # -- statements ------------------------------------------------------

    def parse(self) -> List[nodes.Node]:
        body, end = self._subparse(())
        assert end is None  # _subparse only stops early for `until` keywords
        return body

    def _subparse(
        self, until: Tuple[str, ...]
    ) -> Tuple[List[nodes.Node], Optional[str]]:
        """Parse statements until EOF or a block tag named in *until*.

        The terminating tag is NOT consumed; its keyword is returned so the
        caller can decide how to proceed (e.g. an ``elif`` chain).
        """
        body: List[nodes.Node] = []
        while True:
            tok = self._peek()
            if tok.kind == TOKEN_EOF:
                if until:
                    self._fail(
                        "unexpected end of template, expected "
                        + " or ".join(f"{{% {kw} %}}" for kw in until),
                        tok,
                    )
                return body, None
            if tok.kind == TOKEN_TEXT:
                self._next()
                body.append(nodes.Text(tok.value, tok.line))
                continue
            if tok.kind == TOKEN_VAR_BEGIN:
                self._next()
                expr = self.parse_expression()
                self._expect(TOKEN_VAR_END)
                body.append(nodes.Output(expr, tok.line))
                continue
            # A block tag: peek at the keyword before consuming anything so
            # terminators can be handed back to the enclosing statement.
            kw_tok = self._peek(1)
            if kw_tok.kind != TOKEN_NAME:
                self._fail("expected a statement keyword after '{%'", kw_tok)
            if kw_tok.value in until:
                return body, kw_tok.value
            if kw_tok.value in _END_KEYWORDS:
                self._fail(f"unexpected '{{% {kw_tok.value} %}}'", kw_tok)
            if kw_tok.value not in _STATEMENT_KEYWORDS:
                self._fail(f"unknown statement '{kw_tok.value}'", kw_tok)
            self._next()  # '{%'
            self._next()  # keyword
            body.append(self._parse_statement(kw_tok))

    def _consume_end_tag(self, keyword: str) -> None:
        """Consume ``{% keyword %}`` whose keyword _subparse already matched."""
        self._expect(TOKEN_BLOCK_BEGIN)
        self._expect(TOKEN_NAME, keyword)
        self._expect(TOKEN_BLOCK_END)

    def _parse_statement(self, kw_tok: Token) -> nodes.Node:
        if kw_tok.value == "for":
            return self._parse_for(kw_tok)
        if kw_tok.value == "if":
            return self._parse_if(kw_tok)
        return self._parse_set(kw_tok)

    def _parse_for(self, kw_tok: Token) -> nodes.For:
        target = self._expect(TOKEN_NAME).value
        self._expect(TOKEN_NAME, "in")
        iterable = self.parse_expression()
        self._expect(TOKEN_BLOCK_END)
        body, _end = self._subparse(("endfor",))
        self._consume_end_tag("endfor")
        return nodes.For(target, iterable, body, kw_tok.line)

    def _parse_if(self, kw_tok: Token) -> nodes.If:
        branches: List[Tuple[Optional[nodes.Node], List[nodes.Node]]] = []
        cond: Optional[nodes.Node] = self.parse_expression()
        self._expect(TOKEN_BLOCK_END)
        body, end = self._subparse(("elif", "else", "endif"))
        branches.append((cond, body))
        while end == "elif":
            self._expect(TOKEN_BLOCK_BEGIN)
            self._expect(TOKEN_NAME, "elif")
            cond = self.parse_expression()
            self._expect(TOKEN_BLOCK_END)
            body, end = self._subparse(("elif", "else", "endif"))
            branches.append((cond, body))
        if end == "else":
            self._expect(TOKEN_BLOCK_BEGIN)
            self._expect(TOKEN_NAME, "else")
            self._expect(TOKEN_BLOCK_END)
            body, end = self._subparse(("endif",))
            branches.append((None, body))
        self._consume_end_tag("endif")
        return nodes.If(branches, kw_tok.line)

    def _parse_set(self, kw_tok: Token) -> nodes.SetStmt:
        name = self._expect(TOKEN_NAME).value
        attr: Optional[str] = None
        if self._at_op("."):
            self._next()
            attr = self._expect(TOKEN_NAME).value
        self._expect(TOKEN_OP, "=")
        expr = self.parse_expression()
        self._expect(TOKEN_BLOCK_END)
        return nodes.SetStmt(name, attr, expr, kw_tok.line)

    # -- expressions ------------------------------------------------------

    def parse_expression(self) -> nodes.Node:
        expr = self._parse_or()
        if self._at_name("if"):
            line = self._next().line
            cond = self._parse_or()
            false: Optional[nodes.Node] = None
            if self._at_name("else"):
                self._next()
                false = self.parse_expression()
            return nodes.CondExpr(cond, expr, false, line)
        return expr

    def _parse_or(self) -> nodes.Node:
        left = self._parse_and()
        while self._at_name("or"):
            line = self._next().line
            left = nodes.BinOp("or", left, self._parse_and(), line)
        return left

    def _parse_and(self) -> nodes.Node:
        left = self._parse_not()
        while self._at_name("and"):
            line = self._next().line
            left = nodes.BinOp("and", left, self._parse_not(), line)
        return left

    def _parse_not(self) -> nodes.Node:
        if self._at_name("not"):
            line = self._next().line
            return nodes.UnaryOp("not", self._parse_not(), line)
        return self._parse_compare()

    def _parse_compare(self) -> nodes.Node:
        left = self._parse_concat()
        while True:
            tok = self._peek()
            if tok.kind == TOKEN_OP and tok.value in _COMPARE_OPS:
                self._next()
                left = nodes.BinOp(tok.value, left, self._parse_concat(), tok.line)
            elif self._at_name("in"):
                self._next()
                left = nodes.BinOp("in", left, self._parse_concat(), tok.line)
            elif self._at_name("not") and self._peek(1).value == "in":
                self._next()
                self._next()
                left = nodes.BinOp("not in", left, self._parse_concat(), tok.line)
            elif self._at_name("is"):
                self._next()
                negated = False
                if self._at_name("not"):
                    self._next()
                    negated = True
                test_name = self._expect(TOKEN_NAME).value
                left = nodes.Test(left, test_name, negated, tok.line)
            else:
                return left

    def _parse_concat(self) -> nodes.Node:
        left = self._parse_add()
        while self._at_op("~"):
            line = self._next().line
            left = nodes.BinOp("~", left, self._parse_add(), line)
        return left

    def _parse_add(self) -> nodes.Node:
        left = self._parse_mul()
        while self._at_op("+", "-"):
            tok = self._next()
            left = nodes.BinOp(tok.value, left, self._parse_mul(), tok.line)
        return left

    def _parse_mul(self) -> nodes.Node:
        left = self._parse_unary()
        while self._at_op("*", "/", "%"):
            tok = self._next()
            left = nodes.BinOp(tok.value, left, self._parse_unary(), tok.line)
        return left

    def _parse_unary(self, with_filter: bool = True) -> nodes.Node:
        # Mirrors Jinja: the operand of unary minus is parsed WITHOUT the
        # filter chain, then postfix and filters apply to the whole result —
        # so `-4 | abs` is `(-4) | abs`, not `-(4 | abs)`.
        if self._at_op("-"):
            line = self._next().line
            node: nodes.Node = nodes.UnaryOp(
                "neg", self._parse_unary(with_filter=False), line
            )
        else:
            node = self._parse_primary()
        node = self._parse_postfix(node)
        if with_filter:
            node = self._parse_filters(node)
        return node

    def _parse_postfix(self, node: nodes.Node) -> nodes.Node:
        """Attribute access, subscripts, and calls: ``.name`` ``[expr]`` ``(...)``."""
        while True:
            if self._at_op("."):
                line = self._next().line
                name = self._expect(TOKEN_NAME).value
                node = nodes.GetAttr(node, name, line)
            elif self._at_op("["):
                line = self._next().line
                key = self.parse_expression()
                self._expect(TOKEN_OP, "]")
                node = nodes.GetItem(node, key, line)
            elif self._at_op("("):
                line = self._peek().line
                args, kwargs = self._parse_call_args()
                node = nodes.Call(node, args, kwargs, line)
            else:
                return node

    def _parse_filters(self, node: nodes.Node) -> nodes.Node:
        """A chain of ``| name`` / ``| name(args)`` applications."""
        while self._at_op("|"):
            line = self._next().line
            name = self._expect(TOKEN_NAME).value
            args: List[nodes.Node] = []
            if self._at_op("("):
                args, kwargs = self._parse_call_args()
                if kwargs:
                    self._fail(f"filter '{name}' does not accept keyword arguments")
            node = nodes.Filter(node, name, args, line)
        return node

    def _parse_call_args(self):
        """Parse ``( expr, ..., name=expr, ... )`` including the parens."""
        self._expect(TOKEN_OP, "(")
        args: List[nodes.Node] = []
        kwargs: List[Tuple[str, nodes.Node]] = []
        while not self._at_op(")"):
            if (
                self._peek().kind == TOKEN_NAME
                and self._peek(1).kind == TOKEN_OP
                and self._peek(1).value == "="
            ):
                key = self._next().value
                self._next()  # '='
                kwargs.append((key, self.parse_expression()))
            else:
                if kwargs:
                    self._fail("positional argument follows keyword argument")
                args.append(self.parse_expression())
            if self._at_op(","):
                self._next()
            elif not self._at_op(")"):
                self._fail("expected ',' or ')' in argument list")
        self._next()  # ')'
        return args, kwargs

    def _parse_primary(self) -> nodes.Node:
        tok = self._peek()
        if tok.kind == TOKEN_STRING:
            self._next()
            return nodes.Literal(tok.value, tok.line)
        if tok.kind == TOKEN_NUMBER:
            self._next()
            value = float(tok.value) if "." in tok.value else int(tok.value)
            return nodes.Literal(value, tok.line)
        if tok.kind == TOKEN_NAME:
            self._next()
            if tok.value in ("true", "True"):
                return nodes.Literal(True, tok.line)
            if tok.value in ("false", "False"):
                return nodes.Literal(False, tok.line)
            if tok.value in ("none", "None"):
                return nodes.Literal(None, tok.line)
            return nodes.Name(tok.value, tok.line)
        if tok.kind == TOKEN_OP and tok.value == "(":
            self._next()
            expr = self.parse_expression()
            self._expect(TOKEN_OP, ")")
            return expr
        if tok.kind == TOKEN_OP and tok.value == "[":
            self._next()
            items: List[nodes.Node] = []
            while not self._at_op("]"):
                items.append(self.parse_expression())
                if self._at_op(","):
                    self._next()
                elif not self._at_op("]"):
                    self._fail("expected ',' or ']' in list literal")
            self._next()  # ']'
            return nodes.ListLit(items, tok.line)
        got = tok.value if tok.value else tok.kind
        self._fail(f"unexpected {got!r} in expression", tok)
        raise AssertionError("unreachable")  # pragma: no cover
