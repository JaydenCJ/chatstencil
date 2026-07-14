"""Statement semantics: for/loop.*, if chains, set scoping, namespace,
whitespace control, and raise_exception — the constructs real chat
templates are built from.
"""

import pytest

from chatstencil.errors import TemplateRuntimeError


def test_for_loop_renders_in_order_and_iterates_mapping_keys(render, messages):
    out = render("{% for m in messages %}{{ m.role }};{% endfor %}", messages=messages)
    assert out == "system;user;assistant;user;"
    assert render("{% for k in m %}{{ k }}.{% endfor %}", m={"a": 1, "b": 2}) == "a.b."


def test_loop_variables_including_nested_loops(render):
    src = (
        "{% for x in xs %}"
        "{{ loop.index0 }}:{{ loop.index }}:{{ loop.first }}:{{ loop.last }}"
        ":{{ loop.length }}|"
        "{% endfor %}"
    )
    assert render(src, xs=["a", "b"]) == "0:1:True:False:2|1:2:False:True:2|"
    nested = (
        "{% for a in outer %}{% for b in inner %}"
        "{{ loop.index }}{% endfor %};{% endfor %}"
    )
    assert render(nested, outer=[1, 2], inner=["x", "y", "z"]) == "123;123;"


def test_for_over_undefined_fails_with_target_name(render):
    with pytest.raises(TemplateRuntimeError, match="for message"):
        render("{% for message in mesages %}x{% endfor %}")


def test_elif_chain_picks_first_true_branch(render):
    src = "{% if r == 'a' %}A{% elif r == 'b' %}B{% else %}other{% endif %}"
    assert render(src, r="b") == "B"
    assert render(src, r="z") == "other"


def test_set_is_scoped_to_the_loop_body(render):
    # The classic Jinja gotcha: assignments inside a loop do not leak out.
    src = "{% set x = 'outer' %}{% for i in [1] %}{% set x = 'inner' %}{% endfor %}{{ x }}"
    assert render(src) == "outer"


def test_namespace_carries_state_across_iterations(render, messages):
    src = (
        "{% set ns = namespace(users=0) %}"
        "{% for m in messages %}"
        "{% if m.role == 'user' %}{% set ns.users = ns.users + 1 %}{% endif %}"
        "{% endfor %}"
        "{{ ns.users }}"
    )
    assert render(src, messages=messages) == "2"


def test_set_attribute_on_non_namespace_is_an_error(render):
    with pytest.raises(TemplateRuntimeError, match="namespace"):
        render("{% set m.role = 'x' %}", m={"role": "user"})


def test_raise_exception_aborts_with_the_template_message(render):
    src = (
        "{% for m in messages %}"
        "{% if m.role == 'tool' %}"
        "{{ raise_exception('unsupported role: ' ~ m.role) }}"
        "{% endif %}{% endfor %}"
    )
    with pytest.raises(TemplateRuntimeError, match="unsupported role: tool"):
        render(src, messages=[{"role": "tool", "content": "x"}])


def test_range_is_usable_but_capped(render):
    assert render("{% for i in range(3) %}{{ i }}{% endfor %}") == "012"
    with pytest.raises(TemplateRuntimeError, match="range"):
        render("{% for i in range(1000000) %}x{% endfor %}")


def test_whitespace_control_and_literal_text_preservation(render):
    # `{%-` right-strips preceding text; `-%}` left-strips following text —
    # and everything not explicitly trimmed survives byte-for-byte.
    assert render("a  \n  {%- if true %}  X  {%- endif -%}  \n  b") == "a  Xb"
    src = "  leading\ttab  \n\n{{ 'mid' }}  trailing  "
    assert render(src) == "  leading\ttab  \n\nmid  trailing  "
