# Changelog

All notable changes to this project are documented in this file. The format is
based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-07-13

### Added

- Sandboxed template engine implementing the chat-template subset of Jinja
  on the standard library alone: `{{ }}` / `{% %}` / `{# #}` with whitespace
  control, `for` with full `loop.*` variables, `if`/`elif`/`else`,
  scoped `set`, `namespace()` attribute assignment, inline conditionals,
  and Jinja-faithful undefined semantics (failed subscripts probe as
  `is defined` instead of crashing).
- 22 built-in filters (`trim`, `join`, `default`, `tojson` with sorted keys,
  `indent`, ...), 11 tests (`defined`, `mapping`, ...), an allowlisted
  method surface per type (`str`/`dict`/`list`), and template-level
  `raise_exception(...)` for rejecting unsupported conversations.
- Five byte-exact presets: `chatml`, `inst`, `zephyr`, `alpaca`, `plain`,
  each with its own default special tokens; templates also load from files.
- JSON message fixtures with strict validation (message index in every
  error), directory discovery, duplicate-name rejection, and per-fixture
  `vars` / `add_generation_prompt`.
- Golden workflow: `record` writes the exact rendered string per
  (fixture, template) pair; `check` re-renders and compares byte-for-byte,
  reporting mismatched, missing, and stale goldens with whitespace-visible
  unified diffs (`\n`, `\t`, and backslashes made explicit).
- `chatstencil` CLI: `render` (with `--escape`, `--var`, generation-prompt
  overrides), `record`, `check`, `diff` (two templates, one fixture,
  exit 1 on drift), and `presets`. Exit codes: 0 ok, 1 drift, 2 error,
  141 on a closed output pipe (so `| head` can never read as drift).
- Runnable examples: three fixtures, a custom `support-bot.jinja`, and
  committed goldens that the test suite re-verifies.
- 90 pytest tests and `scripts/smoke.sh` (end-to-end CLI drill that prints
  `SMOKE OK`).

### Notes

- The repository ships no CI workflow; verification is local — `pip install -e '.[dev]' && pytest && bash scripts/smoke.sh`.

[0.1.0]: https://github.com/JaydenCJ/chatstencil/releases/tag/v0.1.0
