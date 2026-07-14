"""Golden record/check round-trips and whitespace-visible diffing.

The check must be byte-exact: a missing final newline or a tab-for-space
swap is precisely the kind of prompt bug that eyeballing misses.
"""

from chatstencil import discover_fixtures, load_template
from chatstencil.golden import (
    STATUS_MISMATCH,
    STATUS_MISSING,
    STATUS_OK,
    STATUS_STALE,
    check_goldens,
    diff_strings,
    escape_lines,
    golden_path,
    record_goldens,
)


def make_setup(write_fixture, tmp_path, template="chatml"):
    write_fixture("convo.json", name="convo")
    fixtures = discover_fixtures([str(tmp_path / "convo.json")])
    loaded = load_template(template)
    goldens = tmp_path / "goldens"
    return loaded, fixtures, goldens


def test_record_then_check_is_byte_identical(write_fixture, tmp_path):
    loaded, fixtures, goldens = make_setup(write_fixture, tmp_path)
    recorded = record_goldens(loaded, fixtures, goldens)
    assert [r.status for r in recorded] == ["written"]
    results = check_goldens(loaded, fixtures, goldens)
    assert [r.status for r in results] == [STATUS_OK]


def test_rerecord_reports_unchanged_then_updated(write_fixture, tmp_path):
    loaded, fixtures, goldens = make_setup(write_fixture, tmp_path)
    record_goldens(loaded, fixtures, goldens)
    assert [r.status for r in record_goldens(loaded, fixtures, goldens)] == [
        "unchanged"
    ]
    path = golden_path(goldens, "convo", "chatml")
    path.write_text(path.read_text(encoding="utf-8") + "extra", encoding="utf-8")
    assert [r.status for r in record_goldens(loaded, fixtures, goldens)] == [
        "updated"
    ]


def test_single_byte_drift_is_a_mismatch_with_a_diff(write_fixture, tmp_path):
    loaded, fixtures, goldens = make_setup(write_fixture, tmp_path)
    record_goldens(loaded, fixtures, goldens)
    path = golden_path(goldens, "convo", "chatml")
    stored = path.read_text(encoding="utf-8")
    path.write_text(stored.replace("<|im_end|>", "<|im_end|> ", 1), encoding="utf-8")
    (result,) = check_goldens(loaded, fixtures, goldens)
    assert result.status == STATUS_MISMATCH
    assert "-" in result.diff and "+" in result.diff


def test_invisible_differences_are_visible_in_the_diff():
    # Missing final newline: the `\n` marker disappears from the last line.
    newline = diff_strings("a\nb\n", "a\nb", "golden", "rendered")
    assert "-b\\n" in newline and "+b" in newline
    # Tab versus spaces shows as an explicit `\t`.
    assert "\\t" in diff_strings("a\tb\n", "a  b\n", "golden", "rendered")
    # Equal strings produce no diff at all.
    assert diff_strings("same\n", "same\n", "a", "b") == ""


def test_escape_lines_marks_newlines_tabs_and_backslashes():
    assert escape_lines("a\n\tb\\c") == ["a\\n", "\\tb\\\\c"]
    # Trailing newline: marker on the last line, no phantom empty line.
    assert escape_lines("x\n") == ["x\\n"]


def test_missing_golden_is_reported(write_fixture, tmp_path):
    loaded, fixtures, goldens = make_setup(write_fixture, tmp_path)
    (result,) = check_goldens(loaded, fixtures, goldens)
    assert result.status == STATUS_MISSING


def test_stale_golden_is_reported(write_fixture, tmp_path):
    loaded, fixtures, goldens = make_setup(write_fixture, tmp_path)
    record_goldens(loaded, fixtures, goldens)
    orphan = goldens / "renamed-fixture--chatml.golden.txt"
    orphan.write_text("orphaned", encoding="utf-8")
    statuses = {r.status for r in check_goldens(loaded, fixtures, goldens)}
    assert statuses == {STATUS_OK, STATUS_STALE}


def test_stale_detection_is_scoped_to_the_template_label(write_fixture, tmp_path):
    # A golden recorded for another template must not be flagged stale.
    loaded, fixtures, goldens = make_setup(write_fixture, tmp_path)
    record_goldens(loaded, fixtures, goldens)
    other = load_template("plain")
    record_goldens(other, fixtures, goldens)
    statuses = [r.status for r in check_goldens(loaded, fixtures, goldens)]
    assert statuses == [STATUS_OK]


def test_golden_filenames_are_sanitized(tmp_path):
    path = golden_path(tmp_path, "a b/c", "my tmpl")
    assert path.name == "a-b-c--my-tmpl.golden.txt"
    assert path.parent == tmp_path
