# Contributing to chatstencil

Thanks for your interest in contributing. Issues, discussions, and pull
requests are all welcome.

## Getting started

You need Python 3.9 or newer; the runtime has zero dependencies and the test
suite needs only pytest.

```bash
git clone https://github.com/JaydenCJ/chatstencil
cd chatstencil
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
bash scripts/smoke.sh
```

`scripts/smoke.sh` exercises the real CLI end-to-end (render, record, check,
forced drift, diff) in a temporary directory and must print `SMOKE OK`.

## Before you open a pull request

1. Format with `python3 -m black src tests` if you have black, or match the
   surrounding style by hand — formatting consistency is enforced in review.
2. `python3 -m pyflakes src tests` (or your linter of choice) must be clean.
3. `pytest` — every test must pass.
4. `bash scripts/smoke.sh` — must print `SMOKE OK`.
5. Add tests for behavior changes; keep logic in pure, unit-testable modules.

## Ground rules

- **No new runtime dependencies.** The engine is standard-library only; that
  is the headline feature. Test-only dependencies belong in the `dev` extra.
- **Byte-exactness is the contract.** Anything that changes a preset's
  rendered bytes, the golden file format, or diff output is a breaking
  change and needs a version bump plus updated goldens in `examples/`.
- **Dialect changes need docs.** New filters, tests, or statements must be
  added to `docs/template-subset.md` in the same pull request, and unknown
  constructs must keep failing loudly.
- **Keep the three READMEs aligned.** `README.md`, `README.zh.md`, and
  `README.ja.md` are line-for-line parallel; update all three when you
  change one (English is the authoritative version).
- No network calls anywhere in the package, no telemetry. Code comments and
  doc comments are written in English.

## Reporting bugs

Please include the template (or preset name), the fixture JSON, the full
command line, and the output of `chatstencil render --escape` for the case —
that is usually enough to reproduce a rendering bug exactly. Mention your
`chatstencil --version`.

## Security

Please do not report security issues in public GitHub issues. Use GitHub's
private vulnerability reporting on this repository instead. The template
engine is sandboxed by allowlist; anything reachable from a template file
beyond the documented surface is a security bug we want to hear about.
