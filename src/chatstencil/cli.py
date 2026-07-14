"""Command-line interface.

Subcommands:

- ``render``  — print the exact prompt string a template produces
- ``record``  — write golden files for template x fixtures
- ``check``   — re-render and compare against goldens (exit 1 on drift)
- ``diff``    — compare two templates on the same fixture (exit 1 if differ)
- ``presets`` — list built-in templates

Exit codes: 0 success, 1 golden mismatch / templates differ, 2 usage or
input error, 141 when the output pipe closes early (the SIGPIPE
convention, e.g. under ``| head``).  All output is plain text on stdout;
errors go to stderr.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import __version__
from .errors import ChatStencilError
from .fixtures import discover_fixtures, load_fixture
from .golden import (
    STATUS_MISMATCH,
    STATUS_MISSING,
    STATUS_OK,
    STATUS_STALE,
    check_goldens,
    diff_strings,
    escape_lines,
    record_goldens,
)
from .presets import PRESETS, load_template
from .template import render_fixture

EXIT_OK = 0
EXIT_DRIFT = 1
EXIT_ERROR = 2
EXIT_PIPE = 141  # 128 + SIGPIPE: the reader of our stdout went away


def _parse_vars(pairs: Optional[List[str]]) -> Dict[str, Any]:
    """Parse repeated ``--var key=value`` options.

    Values are parsed as JSON when possible (so ``--var flag=true`` is a real
    boolean) and fall back to the raw string otherwise.
    """
    result: Dict[str, Any] = {}
    for pair in pairs or []:
        key, sep, value = pair.partition("=")
        if not sep or not key:
            raise ChatStencilError(f"--var expects key=value, got '{pair}'")
        try:
            result[key] = json.loads(value)
        except json.JSONDecodeError:
            result[key] = value
    return result


def _gen_override(args: argparse.Namespace) -> Optional[bool]:
    if args.generation_prompt:
        return True
    if args.no_generation_prompt:
        return False
    return None


def _add_common_render_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "-t",
        "--template",
        required=True,
        help="built-in preset name or path to a template file",
    )
    parser.add_argument(
        "--var",
        action="append",
        metavar="KEY=VALUE",
        help="override a template variable (repeatable; value parsed as JSON "
        "when possible)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--generation-prompt",
        action="store_true",
        help="force add_generation_prompt=true regardless of the fixture",
    )
    group.add_argument(
        "--no-generation-prompt",
        action="store_true",
        help="force add_generation_prompt=false regardless of the fixture",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="chatstencil",
        description="Render chat templates against message fixtures and "
        "golden-test the exact prompt strings.",
    )
    parser.add_argument(
        "--version", action="version", version=f"chatstencil {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_render = sub.add_parser(
        "render", help="render one fixture and print the exact prompt string"
    )
    _add_common_render_options(p_render)
    p_render.add_argument("-f", "--fixture", required=True, help="fixture JSON file")
    p_render.add_argument(
        "--escape",
        action="store_true",
        help="show invisible characters (\\n, \\t, backslashes) explicitly",
    )

    p_record = sub.add_parser(
        "record", help="render fixtures and write golden files"
    )
    _add_common_render_options(p_record)
    p_record.add_argument(
        "-f",
        "--fixtures",
        required=True,
        nargs="+",
        help="fixture files and/or directories of *.json fixtures",
    )
    p_record.add_argument(
        "-g", "--goldens", required=True, help="directory to write goldens into"
    )

    p_check = sub.add_parser(
        "check",
        help="re-render fixtures and compare byte-for-byte against goldens",
    )
    _add_common_render_options(p_check)
    p_check.add_argument(
        "-f",
        "--fixtures",
        required=True,
        nargs="+",
        help="fixture files and/or directories of *.json fixtures",
    )
    p_check.add_argument(
        "-g", "--goldens", required=True, help="directory holding golden files"
    )

    p_diff = sub.add_parser(
        "diff", help="render one fixture through two templates and diff them"
    )
    p_diff.add_argument("template_a", help="first template (preset or file)")
    p_diff.add_argument("template_b", help="second template (preset or file)")
    p_diff.add_argument("-f", "--fixture", required=True, help="fixture JSON file")
    p_diff.add_argument(
        "--var",
        action="append",
        metavar="KEY=VALUE",
        help="override a template variable (repeatable)",
    )
    group = p_diff.add_mutually_exclusive_group()
    group.add_argument(
        "--generation-prompt",
        action="store_true",
        help="force add_generation_prompt=true regardless of the fixture",
    )
    group.add_argument(
        "--no-generation-prompt",
        action="store_true",
        help="force add_generation_prompt=false regardless of the fixture",
    )

    sub.add_parser("presets", help="list built-in template presets")
    return parser


# -- subcommand implementations ---------------------------------------------


def _cmd_render(args: argparse.Namespace) -> int:
    loaded = load_template(args.template)
    fixture = load_fixture(Path(args.fixture))
    rendered = render_fixture(
        loaded.template,
        fixture,
        defaults=loaded.defaults,
        extra_vars=_parse_vars(args.var),
        generation_prompt=_gen_override(args),
    )
    if args.escape:
        sys.stdout.write("\n".join(escape_lines(rendered)) + "\n")
    else:
        sys.stdout.write(rendered)
    return EXIT_OK


def _cmd_record(args: argparse.Namespace) -> int:
    loaded = load_template(args.template)
    fixtures = discover_fixtures(args.fixtures)
    results = record_goldens(
        loaded,
        fixtures,
        Path(args.goldens),
        extra_vars=_parse_vars(args.var),
        generation_prompt=_gen_override(args),
    )
    for result in results:
        print(f"{result.status:9s} {result.path}")
    noun = "golden" if len(results) == 1 else "goldens"
    print(f"{len(results)} {noun} recorded for template '{loaded.label}'")
    return EXIT_OK


def _cmd_check(args: argparse.Namespace) -> int:
    loaded = load_template(args.template)
    fixtures = discover_fixtures(args.fixtures)
    results = check_goldens(
        loaded,
        fixtures,
        Path(args.goldens),
        extra_vars=_parse_vars(args.var),
        generation_prompt=_gen_override(args),
    )
    failures = 0
    for result in results:
        if result.status == STATUS_OK:
            print(f"ok        {result.fixture_name}")
        elif result.status == STATUS_MISMATCH:
            failures += 1
            print(f"MISMATCH  {result.fixture_name}")
            print(result.diff)
        elif result.status == STATUS_MISSING:
            failures += 1
            print(
                f"MISSING   {result.fixture_name} "
                f"(record it: chatstencil record -t {args.template} ...)"
            )
        elif result.status == STATUS_STALE:
            failures += 1
            print(f"STALE     {result.path} (no fixture produces this golden)")
    checked = len(results)
    if failures:
        print(f"{checked} checked, {failures} failing")
        return EXIT_DRIFT
    print(f"{checked} checked, all byte-identical")
    return EXIT_OK


def _cmd_diff(args: argparse.Namespace) -> int:
    loaded_a = load_template(args.template_a)
    loaded_b = load_template(args.template_b)
    fixture = load_fixture(Path(args.fixture))
    extra = _parse_vars(args.var)
    gen = _gen_override(args)
    rendered_a = render_fixture(
        loaded_a.template, fixture, defaults=loaded_a.defaults,
        extra_vars=extra, generation_prompt=gen,
    )
    rendered_b = render_fixture(
        loaded_b.template, fixture, defaults=loaded_b.defaults,
        extra_vars=extra, generation_prompt=gen,
    )
    if rendered_a == rendered_b:
        print(
            f"identical: '{loaded_a.label}' and '{loaded_b.label}' render "
            f"'{fixture.name}' to the same {len(rendered_a)} characters"
        )
        return EXIT_OK
    print(diff_strings(rendered_a, rendered_b, loaded_a.label, loaded_b.label))
    return EXIT_DRIFT


def _cmd_presets(_args: argparse.Namespace) -> int:
    width = max(len(name) for name in PRESETS)
    for name in sorted(PRESETS):
        preset = PRESETS[name]
        defaults = (
            " [defaults: "
            + ", ".join(f"{k}={v!r}" for k, v in sorted(preset.defaults.items()))
            + "]"
            if preset.defaults
            else ""
        )
        print(f"{name:<{width}}  {preset.description}{defaults}")
    return EXIT_OK


_COMMANDS = {
    "render": _cmd_render,
    "record": _cmd_record,
    "check": _cmd_check,
    "diff": _cmd_diff,
    "presets": _cmd_presets,
}


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return _COMMANDS[args.command](args)
    except ChatStencilError as exc:
        print(f"chatstencil: {exc}", file=sys.stderr)
        return EXIT_ERROR
    except BrokenPipeError:
        # Downstream (e.g. `| head`) closed the pipe; exit quietly with the
        # conventional SIGPIPE code instead of tracebacking — and never with
        # 1, which would read as "drift found" to scripts gating on check.
        # Redirect stdout so interpreter shutdown is clean.
        try:
            os.dup2(os.open(os.devnull, os.O_WRONLY), sys.stdout.fileno())
        except (OSError, ValueError):  # stdout has no usable fd (test harness)
            pass
        return EXIT_PIPE


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
