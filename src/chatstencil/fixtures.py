"""Message fixture loading and validation.

A fixture is a JSON file describing one conversation to render::

    {
      "name": "smalltalk",
      "description": "system + one user turn",
      "add_generation_prompt": true,
      "vars": {"bos_token": "<s>"},
      "messages": [
        {"role": "system", "content": "You are terse."},
        {"role": "user", "content": "hi"}
      ]
    }

Only ``messages`` is required.  Validation is strict and error messages name
the file and the offending message index — fixtures are hand-written and the
whole point of this tool is precision.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List

from .errors import FixtureError

#: Variable names the renderer owns; fixtures may not shadow them via `vars`.
RESERVED_VARS = frozenset(("messages", "add_generation_prompt", "loop"))


@dataclass
class Fixture:
    name: str
    messages: List[Dict[str, Any]]
    vars: Dict[str, Any] = field(default_factory=dict)
    add_generation_prompt: bool = True
    description: str = ""
    path: str = ""


def load_fixture(path: Path) -> Fixture:
    """Load and validate a single fixture file."""
    path = Path(path)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise FixtureError(f"{path}: cannot read fixture: {exc}") from None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise FixtureError(f"{path}: invalid JSON: {exc}") from None
    if not isinstance(data, dict):
        raise FixtureError(f"{path}: fixture must be a JSON object")

    messages = _validate_messages(path, data.get("messages"))
    name = data.get("name", path.stem)
    if not isinstance(name, str) or not name.strip():
        raise FixtureError(f"{path}: 'name' must be a non-empty string")

    variables = data.get("vars", {})
    if not isinstance(variables, dict):
        raise FixtureError(f"{path}: 'vars' must be a JSON object")
    reserved = sorted(RESERVED_VARS.intersection(variables))
    if reserved:
        raise FixtureError(
            f"{path}: 'vars' may not shadow reserved names: {', '.join(reserved)}"
        )

    gen = data.get("add_generation_prompt", True)
    if not isinstance(gen, bool):
        raise FixtureError(f"{path}: 'add_generation_prompt' must be a boolean")

    description = data.get("description", "")
    if not isinstance(description, str):
        raise FixtureError(f"{path}: 'description' must be a string")

    return Fixture(
        name=name.strip(),
        messages=messages,
        vars=variables,
        add_generation_prompt=gen,
        description=description,
        path=str(path),
    )


def _validate_messages(path: Path, messages: Any) -> List[Dict[str, Any]]:
    if messages is None:
        raise FixtureError(f"{path}: missing required key 'messages'")
    if not isinstance(messages, list) or not messages:
        raise FixtureError(f"{path}: 'messages' must be a non-empty array")
    for i, message in enumerate(messages):
        if not isinstance(message, dict):
            raise FixtureError(f"{path}: message {i} must be an object")
        role = message.get("role")
        if not isinstance(role, str) or not role:
            raise FixtureError(
                f"{path}: message {i} needs a non-empty string 'role'"
            )
        if "content" not in message:
            raise FixtureError(f"{path}: message {i} is missing 'content'")
        if not isinstance(message["content"], str):
            raise FixtureError(
                f"{path}: message {i} 'content' must be a string "
                "(structured content is not supported in 0.1.0)"
            )
    return messages


def discover_fixtures(paths: Iterable[str]) -> List[Fixture]:
    """Load fixtures from files and/or directories (``*.json``, sorted).

    Duplicate fixture names are rejected: golden files are keyed by fixture
    name, so a collision would silently overwrite a golden.
    """
    fixtures: List[Fixture] = []
    for ref in paths:
        p = Path(ref)
        if p.is_dir():
            files = sorted(p.glob("*.json"))
            if not files:
                raise FixtureError(f"{p}: directory contains no *.json fixtures")
            fixtures.extend(load_fixture(f) for f in files)
        elif p.is_file():
            fixtures.append(load_fixture(p))
        else:
            raise FixtureError(f"{p}: no such fixture file or directory")
    seen: Dict[str, str] = {}
    for fixture in fixtures:
        if fixture.name in seen:
            raise FixtureError(
                f"duplicate fixture name '{fixture.name}' "
                f"({seen[fixture.name]} and {fixture.path})"
            )
        seen[fixture.name] = fixture.path
    return fixtures
