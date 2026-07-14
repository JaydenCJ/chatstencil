"""Built-in filter behavior, including the failure modes.

Filters run inside prompt construction: silent wrong output here becomes a
silently wrong prompt, so errors must be loud and messages must name the
filter.
"""

import pytest

from chatstencil.errors import TemplateRuntimeError


def test_trim_and_case_filters(render):
    assert render("[{{ '  x \\n' | trim }}]") == "[x]"
    assert render("{{ 'sysTem' | upper }}") == "SYSTEM"
    assert render("{{ 'SysTem' | lower }}") == "system"
    assert render("{{ 'hello world' | title }}") == "Hello World"
    assert render("{{ 'hello world' | capitalize }}") == "Hello world"


def test_length_count_and_undefined_length_is_an_error(render):
    assert render("{{ messages | length }}", messages=[1, 2, 3]) == "3"
    assert render("{{ 'abc' | count }}") == "3"
    # A template computing `messages | length` against a typo'd variable
    # must not quietly report 0 turns.
    with pytest.raises(TemplateRuntimeError, match="undefined"):
        render("{{ mesages | length }}")


def test_first_and_last_including_empty_sequence(render):
    assert render("{{ roles | first }}/{{ roles | last }}", roles=["a", "b", "c"]) == "a/c"
    with pytest.raises(TemplateRuntimeError, match="empty sequence"):
        render("{{ messages | first }}", messages=[])


def test_join_with_separator_and_coercion(render):
    assert render("{{ xs | join(', ') }}", xs=["a", 1, "b"]) == "a, 1, b"


def test_replace_with_optional_count(render):
    assert render("{{ 'a.a.a' | replace('.', '-') }}") == "a-a-a"
    assert render("{{ 'a.a.a' | replace('.', '-', 1) }}") == "a-a.a"


def test_default_covers_undefined_and_optionally_falsy(render):
    assert render("{{ missing | default('fb') }}") == "fb"
    assert render("{{ '' | default('fb') }}") == ""
    assert render("{{ '' | default('fb', true) }}") == "fb"
    assert render("{{ missing | d('fb') }}") == "fb"  # Jinja alias


def test_int_filter_parses_or_falls_back(render):
    assert render("{{ '42' | int }}") == "42"
    assert render("{{ 'nope' | int }}") == "0"
    assert render("{{ 'nope' | int(7) }}") == "7"


def test_tojson_is_deterministic_and_indent_pads_continuations(render):
    assert render("{{ m | tojson }}", m={"b": 1, "a": "日本語"}) == '{"a": "日本語", "b": 1}'
    assert render("{{ 'a\\nb' | indent(2) }}") == "a\n  b"


def test_string_reverse_list_and_abs(render):
    assert render("{{ 5 | string }}") == "5"
    assert render("{{ 'abc' | reverse }}") == "cba"
    assert render("{{ m | list | join(',') }}", m={"a": 1, "b": 2}) == "a,b"
    assert render("{{ -4 | abs }}") == "4"


def test_unknown_filter_lists_supported_names(render):
    with pytest.raises(TemplateRuntimeError) as excinfo:
        render("{{ x | frobnicate }}", x=1)
    assert "unknown filter 'frobnicate'" in excinfo.value.message
    assert "tojson" in excinfo.value.message
