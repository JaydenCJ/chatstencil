"""Shared fixtures for the chatstencil test suite.

Everything here is offline and deterministic: templates are strings, message
fixtures are written to pytest's ``tmp_path``, and the CLI runs in-process.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from chatstencil import Template
from chatstencil.cli import main


@pytest.fixture
def render():
    """Compile-and-render helper: ``render(source, **variables) -> str``."""

    def _render(source: str, **variables):
        return Template(source).render(**variables)

    return _render


@pytest.fixture
def messages():
    """A standard four-turn conversation used across the suite."""
    return [
        {"role": "system", "content": "You are terse."},
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
        {"role": "user", "content": "bye"},
    ]


@pytest.fixture
def write_fixture(tmp_path: Path):
    """Write a fixture JSON file into tmp_path and return its path."""

    def _write(filename: str, **payload) -> Path:
        payload.setdefault(
            "messages",
            [
                {"role": "system", "content": "You are terse."},
                {"role": "user", "content": "hi"},
            ],
        )
        path = tmp_path / filename
        path.write_text(json.dumps(payload), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def run_cli(capsys):
    """Run the CLI in-process; returns (exit_code, stdout, stderr)."""

    def _run(*argv: str):
        code = main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return _run
