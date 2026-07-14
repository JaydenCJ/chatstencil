#!/usr/bin/env bash
# Smoke test for chatstencil: render presets and a custom template file,
# record + check goldens, force a drift and verify it is caught with a
# visible diff, and cross-check the committed example goldens.
# Self-contained: pure stdlib, no network, idempotent (works from a clean tree).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python3}"
if [ -x "$ROOT/.venv/bin/python" ]; then
  PYTHON="$ROOT/.venv/bin/python"
fi

# The package has zero runtime dependencies, so running from src/ needs no install.
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
# Leave the tree exactly as we found it: no __pycache__ under src/.
export PYTHONDONTWRITEBYTECODE=1

WORKDIR="$(mktemp -d "${TMPDIR:-/tmp}/chatstencil-smoke.XXXXXX")"
trap 'rm -rf "$WORKDIR"' EXIT

fail() { echo "SMOKE FAIL: $1" >&2; exit 1; }

echo "[smoke] python: $("$PYTHON" --version 2>&1)"

# 1. Render the chatml preset; the exact turn markers must be present.
render_out="$("$PYTHON" -m chatstencil render -t chatml \
  -f "$ROOT/examples/fixtures/smalltalk.json")" || fail "render exited non-zero"
echo "$render_out" | sed 's/^/[render] /'
printf '%s' "$render_out" | grep -q "<|im_start|>system" || fail "chatml missing system marker"
printf '%s' "$render_out" | grep -q "<|im_start|>assistant" || fail "chatml missing generation prompt"

# 2. Render a template file with --escape: newlines must be visible as \n.
escape_out="$("$PYTHON" -m chatstencil render -t "$ROOT/examples/templates/support-bot.jinja" \
  -f "$ROOT/examples/fixtures/no-system.json" --escape)" || fail "escape render exited non-zero"
printf '%s' "$escape_out" | grep -q '<|im_start|>user\\n' || fail "--escape did not show \\n markers"

# 3. Record goldens for all example fixtures, then check byte-identically.
"$PYTHON" -m chatstencil record -t chatml \
  -f "$ROOT/examples/fixtures" -g "$WORKDIR/goldens" >/dev/null \
  || fail "record exited non-zero"
[ -f "$WORKDIR/goldens/smalltalk--chatml.golden.txt" ] || fail "golden file missing"
check_out="$("$PYTHON" -m chatstencil check -t chatml \
  -f "$ROOT/examples/fixtures" -g "$WORKDIR/goldens")" || fail "clean check exited non-zero"
echo "$check_out" | sed 's/^/[check] /'
echo "$check_out" | grep -q "3 checked, all byte-identical" || fail "check did not confirm 3 goldens"

# 4. Introduce one-byte drift in a golden; check must exit 1 with a diff.
"$PYTHON" -c "
from pathlib import Path
p = Path('$WORKDIR/goldens/smalltalk--chatml.golden.txt')
p.write_text(p.read_text().replace('concise', 'consise', 1))
"
set +e
drift_out="$("$PYTHON" -m chatstencil check -t chatml \
  -f "$ROOT/examples/fixtures" -g "$WORKDIR/goldens")"
drift_rc=$?
set -e
[ "$drift_rc" -eq 1 ] || fail "check on drift should exit 1, got $drift_rc"
echo "$drift_out" | grep -q "MISMATCH  smalltalk" || fail "drift not reported as MISMATCH"
echo "$drift_out" | grep -q -- "+You are a concise assistant" || fail "diff missing rendered side"
echo "$drift_out" | sed -n '1,6p' | sed 's/^/[drift] /'

# 5. diff: two presets differ (exit 1, labelled); a preset equals itself (exit 0).
set +e
diff_out="$("$PYTHON" -m chatstencil diff chatml zephyr \
  -f "$ROOT/examples/fixtures/smalltalk.json")"
diff_rc=$?
set -e
[ "$diff_rc" -eq 1 ] || fail "diff of different templates should exit 1, got $diff_rc"
echo "$diff_out" | grep -q -- "+++ zephyr" || fail "diff missing template labels"
same_out="$("$PYTHON" -m chatstencil diff plain plain \
  -f "$ROOT/examples/fixtures/smalltalk.json")" \
  || fail "diff of identical templates should exit 0"
echo "$same_out" | grep -q "^identical:" || fail "diff should report identical"

# 6. The committed example goldens must still be byte-identical.
"$PYTHON" -m chatstencil check -t "$ROOT/examples/templates/support-bot.jinja" \
  -f "$ROOT/examples/fixtures" -g "$ROOT/examples/goldens" >/dev/null \
  || fail "committed example goldens drifted"

# 7. presets lists all built-ins; --version agrees with the package.
# (Capture first: `python | grep -q` under pipefail can fail spuriously when
# grep exits at the first match and python's remaining writes hit EPIPE.)
presets_out="$("$PYTHON" -m chatstencil presets)" || fail "presets exited non-zero"
printf '%s\n' "$presets_out" | grep -q "^chatml" || fail "presets missing chatml"
version_out="$("$PYTHON" -m chatstencil --version)"
pkg_version="$("$PYTHON" -c 'import chatstencil; print(chatstencil.__version__)')"
[ "$version_out" = "chatstencil $pkg_version" ] \
  || fail "--version mismatch: '$version_out' vs package '$pkg_version'"

echo "SMOKE OK"
