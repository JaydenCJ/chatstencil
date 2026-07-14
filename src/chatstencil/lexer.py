"""Tokenizer for the chatstencil template dialect.

The dialect is the subset of Jinja that real chat templates actually use:
``{{ expression }}`` outputs, ``{% statement %}`` blocks, ``{# comments #}``,
and the ``-`` whitespace-control markers on any of the three delimiters.
Everything between delimiters is literal text and is preserved byte-for-byte
(that is the whole point of golden-testing prompt strings).

The tokenizer is a single linear scan.  Whitespace control is applied here,
during emission: ``{%-`` right-strips the preceding text token and ``-%}``
left-strips the following one, exactly like Jinja.
"""

from __future__ import annotations

from typing import List, Optional

from .errors import TemplateSyntaxError

TOKEN_TEXT = "text"
TOKEN_VAR_BEGIN = "var_begin"
TOKEN_VAR_END = "var_end"
TOKEN_BLOCK_BEGIN = "block_begin"
TOKEN_BLOCK_END = "block_end"
TOKEN_NAME = "name"
TOKEN_STRING = "string"
TOKEN_NUMBER = "number"
TOKEN_OP = "op"
TOKEN_EOF = "eof"

# Multi-character operators must be matched before single-character ones.
_TWO_CHAR_OPS = ("==", "!=", "<=", ">=")
_ONE_CHAR_OPS = frozenset("+-*/%~|.,:()[]<>=")

_STRING_ESCAPES = {
    "n": "\n",
    "t": "\t",
    "r": "\r",
    "\\": "\\",
    "'": "'",
    '"': '"',
}


class Token:
    """A single lexical token with its 1-based source line."""

    __slots__ = ("kind", "value", "line")

    def __init__(self, kind: str, value: str, line: int):
        self.kind = kind
        self.value = value
        self.line = line

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Token({self.kind!r}, {self.value!r}, line={self.line})"


def tokenize(source: str, name: str = "<template>") -> List[Token]:
    """Tokenize *source* into a flat token list ending with an EOF token."""
    return _Lexer(source, name).run()


class _Lexer:
    def __init__(self, source: str, name: str):
        self.source = source
        self.name = name
        self.pos = 0
        self.line = 1
        self.tokens: List[Token] = []
        # Set when a closing delimiter carried ``-``: the next text token
        # must be left-stripped.
        self.strip_next_text = False

    def run(self) -> List[Token]:
        src = self.source
        n = len(src)
        while self.pos < n:
            open_at = self._find_next_delimiter()
            if open_at is None:
                self._emit_text(src[self.pos :], trim_right=False)
                self.pos = n
                break
            marker = src[open_at : open_at + 2]
            trim_left = src.startswith("-", open_at + 2)
            self._emit_text(src[self.pos : open_at], trim_right=trim_left)
            self.pos = open_at + (3 if trim_left else 2)
            if marker == "{#":
                self._consume_comment()
            elif marker == "{{":
                self.tokens.append(Token(TOKEN_VAR_BEGIN, "{{", self.line))
                self._scan_expression("}}", TOKEN_VAR_END)
            else:  # "{%"
                self.tokens.append(Token(TOKEN_BLOCK_BEGIN, "{%", self.line))
                self._scan_expression("%}", TOKEN_BLOCK_END)
        self.tokens.append(Token(TOKEN_EOF, "", self.line))
        return self.tokens

    # -- text and comments -------------------------------------------------

    def _find_next_delimiter(self) -> Optional[int]:
        """Index of the next ``{{``/``{%``/``{#``, or None."""
        i = self.pos
        src = self.source
        while True:
            j = src.find("{", i)
            if j == -1 or j + 1 >= len(src):
                return None
            if src[j + 1] in "{%#":
                return j
            i = j + 1

    def _emit_text(self, text: str, trim_right: bool) -> None:
        raw = text
        if self.strip_next_text:
            text = text.lstrip()
            self.strip_next_text = False
        if trim_right:
            text = text.rstrip()
        if text:
            self.tokens.append(Token(TOKEN_TEXT, text, self.line))
        # Line numbers advance by the raw text, including stripped newlines.
        self.line += raw.count("\n")

    def _consume_comment(self) -> None:
        start_line = self.line
        end = self.source.find("#}", self.pos)
        if end == -1:
            raise TemplateSyntaxError("unterminated comment '{#'", self.name, start_line)
        body = self.source[self.pos : end]
        self.line += body.count("\n")
        if body.endswith("-"):
            self.strip_next_text = True
        self.pos = end + 2

    # -- expressions --------------------------------------------------------

    def _scan_expression(self, closer: str, end_kind: str) -> None:
        """Tokenize expression content until *closer* (or ``-closer``)."""
        src = self.source
        n = len(src)
        start_line = self.line
        while self.pos < n:
            c = src[self.pos]
            if c in " \t\r\n":
                if c == "\n":
                    self.line += 1
                self.pos += 1
                continue
            if c == "-" and src.startswith(closer, self.pos + 1):
                self.tokens.append(Token(end_kind, closer, self.line))
                self.pos += 1 + len(closer)
                self.strip_next_text = True
                return
            if src.startswith(closer, self.pos):
                self.tokens.append(Token(end_kind, closer, self.line))
                self.pos += len(closer)
                return
            if c.isalpha() or c == "_":
                self._scan_name()
            elif c.isdigit():
                self._scan_number()
            elif c in "'\"":
                self._scan_string(c)
            else:
                self._scan_operator(closer)
        raise TemplateSyntaxError(
            f"unterminated expression, expected '{closer}'", self.name, start_line
        )

    def _scan_name(self) -> None:
        src = self.source
        start = self.pos
        while self.pos < len(src) and (src[self.pos].isalnum() or src[self.pos] == "_"):
            self.pos += 1
        self.tokens.append(Token(TOKEN_NAME, src[start : self.pos], self.line))

    def _scan_number(self) -> None:
        src = self.source
        start = self.pos
        while self.pos < len(src) and src[self.pos].isdigit():
            self.pos += 1
        if (
            self.pos + 1 < len(src)
            and src[self.pos] == "."
            and src[self.pos + 1].isdigit()
        ):
            self.pos += 1
            while self.pos < len(src) and src[self.pos].isdigit():
                self.pos += 1
        self.tokens.append(Token(TOKEN_NUMBER, src[start : self.pos], self.line))

    def _scan_string(self, quote: str) -> None:
        src = self.source
        start_line = self.line
        self.pos += 1
        parts: List[str] = []
        while self.pos < len(src):
            c = src[self.pos]
            if c == quote:
                self.pos += 1
                self.tokens.append(Token(TOKEN_STRING, "".join(parts), start_line))
                return
            if c == "\\":
                if self.pos + 1 >= len(src):
                    break
                esc = src[self.pos + 1]
                parts.append(_STRING_ESCAPES.get(esc, "\\" + esc))
                self.pos += 2
                continue
            if c == "\n":
                self.line += 1
            parts.append(c)
            self.pos += 1
        raise TemplateSyntaxError("unterminated string literal", self.name, start_line)

    def _scan_operator(self, closer: str) -> None:
        src = self.source
        two = src[self.pos : self.pos + 2]
        if two in _TWO_CHAR_OPS:
            self.tokens.append(Token(TOKEN_OP, two, self.line))
            self.pos += 2
            return
        c = src[self.pos]
        # ``%`` is both the modulo operator and the first byte of ``%}``;
        # the closer was already checked above, so a bare ``%`` here is modulo.
        if c in _ONE_CHAR_OPS:
            self.tokens.append(Token(TOKEN_OP, c, self.line))
            self.pos += 1
            return
        raise TemplateSyntaxError(
            f"unexpected character {c!r} in expression", self.name, self.line
        )
