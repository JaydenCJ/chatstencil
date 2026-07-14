"""The committed examples must keep working: their goldens are checked here
byte-for-byte, so the `examples/` directory can never silently rot.
"""

from pathlib import Path

import pytest

from chatstencil import discover_fixtures, load_template
from chatstencil.errors import TemplateRuntimeError
from chatstencil.golden import STATUS_OK, check_goldens
from chatstencil.template import render_fixture

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def example_fixtures():
    return discover_fixtures([str(EXAMPLES / "fixtures")])


def test_committed_chatml_goldens_are_byte_identical():
    loaded = load_template("chatml")
    results = check_goldens(loaded, example_fixtures(), EXAMPLES / "goldens")
    assert [r.status for r in results] == [STATUS_OK] * 3


def test_committed_support_bot_goldens_are_byte_identical():
    loaded = load_template(str(EXAMPLES / "templates" / "support-bot.jinja"))
    assert loaded.label == "support-bot"
    results = check_goldens(loaded, example_fixtures(), EXAMPLES / "goldens")
    assert [r.status for r in results] == [STATUS_OK] * 3


def test_support_bot_enforces_a_single_leading_system_message():
    loaded = load_template(str(EXAMPLES / "templates" / "support-bot.jinja"))
    fixture = example_fixtures()[0]
    fixture.messages = [
        {"role": "user", "content": "hi"},
        {"role": "system", "content": "late system prompt"},
    ]
    with pytest.raises(TemplateRuntimeError, match="single leading system message"):
        render_fixture(loaded.template, fixture, defaults=loaded.defaults)
