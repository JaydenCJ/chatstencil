"""Fixture loading and validation.

Fixtures are hand-written JSON; every malformed shape must be rejected with
the file name and message index in the error, never rendered half-right.
"""

import pytest

from chatstencil import discover_fixtures, load_fixture
from chatstencil.errors import FixtureError


def test_minimal_fixture_gets_defaults(write_fixture):
    path = write_fixture("convo.json")
    fixture = load_fixture(path)
    assert fixture.name == "convo"  # defaults to the file stem
    assert fixture.add_generation_prompt is True
    assert fixture.vars == {}
    assert fixture.messages[0]["role"] == "system"


def test_explicit_name_vars_and_flags_are_honored(write_fixture):
    path = write_fixture(
        "f.json",
        name="smalltalk",
        vars={"bos_token": "<s>"},
        add_generation_prompt=False,
        description="two turns",
    )
    fixture = load_fixture(path)
    assert fixture.name == "smalltalk"
    assert fixture.vars == {"bos_token": "<s>"}
    assert fixture.add_generation_prompt is False


def test_missing_messages_and_invalid_json_are_rejected(tmp_path):
    no_messages = tmp_path / "bad.json"
    no_messages.write_text('{"name": "x"}', encoding="utf-8")
    with pytest.raises(FixtureError, match="missing required key 'messages'"):
        load_fixture(no_messages)
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    with pytest.raises(FixtureError, match="broken.json.*invalid JSON"):
        load_fixture(broken)


def test_malformed_messages_name_the_offending_index(write_fixture):
    missing_role = write_fixture(
        "bad1.json",
        messages=[{"role": "user", "content": "a"}, {"content": "b"}],
    )
    with pytest.raises(FixtureError, match="message 1 needs a non-empty string 'role'"):
        load_fixture(missing_role)
    structured = write_fixture(
        "bad2.json", messages=[{"role": "user", "content": ["parts"]}]
    )
    with pytest.raises(FixtureError, match="message 0 'content' must be a string"):
        load_fixture(structured)


def test_vars_may_not_shadow_reserved_names(write_fixture):
    path = write_fixture("bad.json", vars={"messages": [], "bos_token": ""})
    with pytest.raises(FixtureError, match="reserved names: messages"):
        load_fixture(path)


def test_discover_directory_loads_sorted_json_files(write_fixture, tmp_path):
    write_fixture("b.json", name="beta")
    write_fixture("a.json", name="alpha")
    fixtures = discover_fixtures([str(tmp_path)])
    assert [f.name for f in fixtures] == ["alpha", "beta"]


def test_discover_rejects_duplicate_fixture_names(write_fixture, tmp_path):
    # Goldens are keyed by fixture name; duplicates would overwrite silently.
    write_fixture("one.json", name="same")
    write_fixture("two.json", name="same")
    with pytest.raises(FixtureError, match="duplicate fixture name 'same'"):
        discover_fixtures([str(tmp_path)])


def test_discover_missing_path_and_empty_dir_fail(tmp_path):
    with pytest.raises(FixtureError, match="no such fixture"):
        discover_fixtures([str(tmp_path / "nope.json")])
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(FixtureError, match="no \\*.json fixtures"):
        discover_fixtures([str(empty)])
