"""Tokenizer behavior: delimiters, whitespace control, strings, errors.

The lexer must preserve literal text byte-for-byte — a single swallowed
space in a chat template changes tokenization downstream, which is exactly
the class of bug chatstencil exists to expose.
"""

import pytest

from chatstencil.errors import TemplateSyntaxError
from chatstencil.lexer import tokenize


def kinds(source):
    return [t.kind for t in tokenize(source)]


def test_plain_text_is_a_single_preserved_token():
    tokens = tokenize("hello  \n\tworld")
    assert tokens[0].kind == "text"
    assert tokens[0].value == "hello  \n\tworld"
    assert tokens[-1].kind == "eof"


def test_output_and_block_delimiters():
    assert kinds("a{{ x }}b") == ["text", "var_begin", "name", "var_end", "text", "eof"]
    assert kinds("{% if x %}") == ["block_begin", "name", "name", "block_end", "eof"]


def test_comments_are_dropped_entirely():
    tokens = tokenize("a{# any {{ x }} inside #}b")
    assert [(t.kind, t.value) for t in tokens] == [
        ("text", "a"),
        ("text", "b"),
        ("eof", ""),
    ]


def test_whitespace_control_trims_adjacent_text():
    # `{%-` strips the text to its left, `-%}` strips to its right.
    tokens = tokenize("a  \n {%- if x -%} \n b")
    texts = [t.value for t in tokens if t.kind == "text"]
    assert texts == ["a", "b"]


def test_string_escapes_are_decoded():
    tokens = tokenize(r"{{ 'a\n\t\\b' }}")
    strings = [t.value for t in tokens if t.kind == "string"]
    assert strings == ["a\n\t\\b"]


def test_two_char_operators_win_over_single_char():
    ops = [t.value for t in tokenize("{{ a <= b == c }}") if t.kind == "op"]
    assert ops == ["<=", "=="]


def test_unterminated_expression_reports_its_line():
    with pytest.raises(TemplateSyntaxError) as excinfo:
        tokenize("ok\n{{ x ")
    assert "unterminated expression" in str(excinfo.value)
    assert ":2:" in str(excinfo.value)


def test_malformed_input_raises_named_errors():
    with pytest.raises(TemplateSyntaxError, match="unterminated string"):
        tokenize("{{ 'oops }}")
    with pytest.raises(TemplateSyntaxError, match="unexpected character"):
        tokenize("{{ a ? b }}")
    with pytest.raises(TemplateSyntaxError, match="unterminated comment"):
        tokenize("{# never closed")
