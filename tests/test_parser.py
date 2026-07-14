"""Parser structure and syntax-error reporting.

Templates are copied from model repos and hand-edited; a parser that fails
with the wrong line number (or accepts garbage) wastes the debugging session
this tool is supposed to shorten.
"""

import pytest

from chatstencil import Template
from chatstencil import nodes
from chatstencil.errors import TemplateSyntaxError


def body_of(source):
    return Template(source).body


def test_if_elif_else_collects_all_branches():
    tree = body_of("{% if a %}1{% elif b %}2{% elif c %}3{% else %}4{% endif %}")
    (if_node,) = tree
    assert isinstance(if_node, nodes.If)
    assert len(if_node.branches) == 4
    assert if_node.branches[-1][0] is None  # else branch has no condition


def test_nested_for_loops_nest_in_the_tree():
    tree = body_of("{% for a in xs %}{% for b in ys %}x{% endfor %}{% endfor %}")
    outer = tree[0]
    assert isinstance(outer, nodes.For)
    inner = outer.body[0]
    assert isinstance(inner, nodes.For)
    assert isinstance(inner.body[0], nodes.Text)


def test_unclosed_for_names_the_missing_tag():
    with pytest.raises(TemplateSyntaxError, match=r"expected \{% endfor %\}"):
        body_of("{% for m in messages %}{{ m }}")


def test_misplaced_end_tags_are_rejected():
    with pytest.raises(TemplateSyntaxError, match="unexpected '{% endif %}'"):
        body_of("hello {% endif %}")
    with pytest.raises(TemplateSyntaxError):
        body_of("{% if a %}1{% else %}2{% else %}3{% endif %}")


def test_unknown_statement_is_rejected_with_its_name():
    with pytest.raises(TemplateSyntaxError, match="unknown statement 'include'"):
        body_of("{% include 'other' %}")


def test_bad_call_argument_lists_are_rejected():
    with pytest.raises(TemplateSyntaxError, match="keyword arguments"):
        body_of("{{ x | default(fallback='y') }}")
    with pytest.raises(TemplateSyntaxError, match="positional argument follows"):
        body_of("{{ namespace(a=1, 2) }}")


def test_syntax_error_line_number_points_at_the_bad_tag():
    source = "line one\nline two\n{% endfor %}"
    with pytest.raises(TemplateSyntaxError) as excinfo:
        body_of(source)
    assert excinfo.value.line == 3
