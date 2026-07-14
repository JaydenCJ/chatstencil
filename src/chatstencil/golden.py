"""Golden-file recording, checking, and whitespace-visible diffing.

A golden file stores the **exact** rendered prompt string, byte-for-byte
(written with newline translation disabled).  Checking re-renders every
fixture and compares against the stored string; mismatches produce a unified
diff in which every newline, tab, and backslash is made visible, because the
bugs this tool exists to catch usually live in the invisible characters.

Golden files are named ``<fixture>--<label>.golden.txt`` inside the goldens
directory, where *label* is the preset name or the template file's stem.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from .fixtures import Fixture
from .presets import LoadedTemplate
from .template import render_fixture

GOLDEN_SUFFIX = ".golden.txt"

STATUS_OK = "ok"
STATUS_MISMATCH = "mismatch"
STATUS_MISSING = "missing"
STATUS_STALE = "stale"


@dataclass
class GoldenResult:
    fixture_name: str
    path: Path
    status: str
    diff: str = ""


def _sanitize(part: str) -> str:
    """Make a fixture/template name safe as a file-name component."""
    return re.sub(r"[^A-Za-z0-9._-]+", "-", part).strip("-") or "unnamed"


def golden_path(directory: Path, fixture_name: str, label: str) -> Path:
    return Path(directory) / (
        f"{_sanitize(fixture_name)}--{_sanitize(label)}{GOLDEN_SUFFIX}"
    )


def escape_lines(text: str) -> List[str]:
    r"""Split *text* into display lines with invisible characters made visible.

    Backslashes are doubled, tabs become ``\t``, and every line that ends in a
    newline gets a trailing ``\n`` marker — so a missing final newline (the
    classic template bug) is visible in a diff instead of vanishing.
    """
    lines = text.split("\n")
    visible: List[str] = []
    for i, line in enumerate(lines):
        shown = line.replace("\\", "\\\\").replace("\t", "\\t")
        if i < len(lines) - 1:
            shown += "\\n"
        visible.append(shown)
    # A trailing newline leaves an empty final chunk; drop the empty display
    # line so diffs stay tight (the `\n` marker on the previous line covers it).
    if len(visible) > 1 and visible[-1] == "":
        visible.pop()
    return visible


def diff_strings(a: str, b: str, from_label: str, to_label: str) -> str:
    """Unified, whitespace-visible diff of two rendered strings ('' if equal)."""
    if a == b:
        return ""
    diff = difflib.unified_diff(
        escape_lines(a),
        escape_lines(b),
        fromfile=from_label,
        tofile=to_label,
        lineterm="",
    )
    return "\n".join(diff)


def _read_exact(path: Path) -> str:
    """Read a golden byte-exactly (no newline translation)."""
    with open(path, "r", encoding="utf-8", newline="") as fh:
        return fh.read()


def _write_exact(path: Path, text: str) -> None:
    with open(path, "w", encoding="utf-8", newline="") as fh:
        fh.write(text)


def record_goldens(
    loaded: LoadedTemplate,
    fixtures: List[Fixture],
    directory: Path,
    extra_vars: Optional[Dict[str, Any]] = None,
    generation_prompt: Optional[bool] = None,
) -> List[GoldenResult]:
    """Render every fixture and write/refresh its golden file.

    Returns one result per fixture with status ``"written"``, ``"updated"``,
    or ``"unchanged"``.
    """
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    results: List[GoldenResult] = []
    for fixture in fixtures:
        rendered = render_fixture(
            loaded.template,
            fixture,
            defaults=loaded.defaults,
            extra_vars=extra_vars,
            generation_prompt=generation_prompt,
        )
        path = golden_path(directory, fixture.name, loaded.label)
        if not path.exists():
            status = "written"
        elif _read_exact(path) == rendered:
            status = "unchanged"
        else:
            status = "updated"
        if status != "unchanged":
            _write_exact(path, rendered)
        results.append(GoldenResult(fixture.name, path, status))
    return results


def check_goldens(
    loaded: LoadedTemplate,
    fixtures: List[Fixture],
    directory: Path,
    extra_vars: Optional[Dict[str, Any]] = None,
    generation_prompt: Optional[bool] = None,
) -> List[GoldenResult]:
    """Re-render every fixture and compare against its stored golden.

    Also reports **stale** goldens: files for this template label with no
    matching fixture (usually a renamed or deleted fixture) — silently
    passing stale goldens would defeat the point of the check.
    """
    directory = Path(directory)
    results: List[GoldenResult] = []
    expected: set = set()
    for fixture in fixtures:
        path = golden_path(directory, fixture.name, loaded.label)
        expected.add(path)
        rendered = render_fixture(
            loaded.template,
            fixture,
            defaults=loaded.defaults,
            extra_vars=extra_vars,
            generation_prompt=generation_prompt,
        )
        if not path.exists():
            results.append(GoldenResult(fixture.name, path, STATUS_MISSING))
            continue
        stored = _read_exact(path)
        if stored == rendered:
            results.append(GoldenResult(fixture.name, path, STATUS_OK))
        else:
            diff = diff_strings(
                stored, rendered, f"golden:{path.name}", "rendered:now"
            )
            results.append(
                GoldenResult(fixture.name, path, STATUS_MISMATCH, diff)
            )
    label_glob = f"*--{_sanitize(loaded.label)}{GOLDEN_SUFFIX}"
    if directory.is_dir():
        for path in sorted(directory.glob(label_glob)):
            if path not in expected:
                results.append(GoldenResult(path.name, path, STATUS_STALE))
    return results
