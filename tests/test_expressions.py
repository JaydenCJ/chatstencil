"""Expression evaluation: operators, precedence, undefined semantics, safety.

These pin the Jinja-compatible behaviors chat templates depend on — e.g.
``messages[0] is defined`` on an empty list must be false, not a crash.
"""

import pytest

from chatstencil.errors import TemplateRuntimeError


def test_arithmetic_precedence_and_numeric_operators(render):
    assert render("{{ 1 + 2 * 3 }}") == "7"
    assert render("{{ (1 + 2) * 3 }}") == "9"
    assert render("{{ 7 % 2 }};{{ 6 / 3 }};{{ -3 + 5 }}") == "1;2.0;2"
    with pytest.raises(TemplateRuntimeError, match="division by zero"):
        render("{{ 1 / 0 }}")


def test_concat_coerces_and_binds_looser_than_plus(render):
    assert render("{{ 'v' ~ 0 ~ '.' ~ 1 }}") == "v0.1"
    # `a ~ b + c` must be a ~ (b + c), as in Jinja.
    assert render("{{ 'n=' ~ 1 + 2 }}") == "n=3"


def test_comparisons_membership_and_boolean_logic(render):
    assert render("{{ 2 >= 2 and 1 != 2 }}") == "True"
    assert render("{{ 1 > 2 or 'x' == 'x' }}") == "True"
    assert render("{{ not (1 < 2) }}") == "False"
    assert render("{{ 'user' in roles }}", roles=["user", "system"]) == "True"
    assert render("{{ 'tool' not in 'user,system' }}") == "True"


def test_and_or_return_operands_like_jinja(render):
    assert render("{{ '' or 'fallback' }}") == "fallback"
    assert render("{{ 'left' and 'right' }}") == "right"


def test_inline_if_with_and_without_else(render):
    assert render("{{ 'a' if true else 'b' }}") == "a"
    assert render("{{ 'a' if false else 'b' }}") == "b"
    # Without else, a false condition renders as empty (undefined).
    assert render("[{{ 'a' if false }}]") == "[]"


def test_undefined_is_empty_falsy_and_detectable(render):
    assert render("[{{ missing }}]") == "[]"
    assert render("{{ 'y' if missing else 'n' }}") == "n"
    assert render("{{ x is defined }}", x=0) == "True"
    assert render("{{ x is not defined }}") == "True"


def test_none_renders_as_python_none_not_empty(render):
    # Matching Jinja here is deliberate: a template that prints None is a
    # bug, and hiding it would defeat golden-testing.
    assert render("{{ none }}") == "None"


def test_failed_subscripts_resolve_to_undefined_not_a_crash(render):
    assert render("{{ messages[0] is defined }}", messages=[]) == "False"
    assert render("{{ messages[0].role }}", messages=[{"role": "user"}]) == "user"
    assert render("{{ m.name is defined }}", m={"role": "user"}) == "False"


def test_attribute_of_undefined_fails_loudly(render):
    with pytest.raises(TemplateRuntimeError, match="undefined"):
        render("{{ missing.role }}")


def test_allowlisted_string_methods_work(render):
    assert render("{{ ' pad '.strip() }}") == "pad"
    assert render("{{ 'a-b'.split('-')[1] }}") == "b"
    assert render("{{ role.startswith('sys') }}", role="system") == "True"


def test_sandbox_blocks_unlisted_methods_and_globals(render):
    # `.format()` and friends are the sandbox escape hatch in real Jinja
    # exploits; the allowlist must reject them by name.
    with pytest.raises(TemplateRuntimeError, match="not allowed"):
        render("{{ 'x'.format() }}")
    with pytest.raises(TemplateRuntimeError, match="not allowed"):
        render("{{ x.mro() }}", x="s")
    with pytest.raises(TemplateRuntimeError, match="not callable"):
        render("{{ open('/etc/hosts') }}")


def test_runtime_type_error_reports_template_line(render):
    with pytest.raises(TemplateRuntimeError) as excinfo:
        render("line1\n{{ 1 + 'x' }}")
    assert excinfo.value.line == 2
    assert "unsupported operand" in excinfo.value.message
