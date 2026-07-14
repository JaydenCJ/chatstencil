"""End-to-end CLI behavior, run in-process for speed and determinism.

Exit codes are part of the contract (0 ok, 1 drift, 2 error) because
`chatstencil check` is designed to gate commits without any CI service.
"""

import sys

import pytest

import chatstencil
from chatstencil.cli import main


def test_render_prints_the_exact_string_no_extra_newline(run_cli, write_fixture):
    path = write_fixture("convo.json")
    code, out, err = run_cli("render", "-t", "chatml", "-f", str(path))
    assert code == 0 and err == ""
    assert out == (
        "<|im_start|>system\nYou are terse.<|im_end|>\n"
        "<|im_start|>user\nhi<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def test_render_escape_makes_newlines_visible(run_cli, write_fixture):
    path = write_fixture("convo.json")
    code, out, _ = run_cli("render", "-t", "chatml", "-f", str(path), "--escape")
    assert code == 0
    assert "<|im_start|>system\\n" in out


def test_render_from_a_template_file(run_cli, write_fixture, tmp_path):
    template = tmp_path / "shout.jinja"
    template.write_text(
        "{% for m in messages %}{{ m.role | upper }}!{% endfor %}", encoding="utf-8"
    )
    path = write_fixture("convo.json")
    code, out, _ = run_cli("render", "-t", str(template), "-f", str(path))
    assert code == 0
    assert out == "SYSTEM!USER!"


def test_var_overrides_are_json_parsed(run_cli, write_fixture, tmp_path):
    template = tmp_path / "t.jinja"
    template.write_text("{{ bos_token }}{{ n + 1 }}", encoding="utf-8")
    path = write_fixture("convo.json")
    code, out, _ = run_cli(
        "render", "-t", str(template), "-f", str(path),
        "--var", "bos_token=<s>", "--var", "n=41",
    )
    assert code == 0
    assert out == "<s>42"


def test_generation_prompt_flags_override_the_fixture(run_cli, write_fixture):
    path = write_fixture("convo.json", add_generation_prompt=True)
    _, with_gen, _ = run_cli("render", "-t", "chatml", "-f", str(path))
    _, without, _ = run_cli(
        "render", "-t", "chatml", "-f", str(path), "--no-generation-prompt"
    )
    assert with_gen.endswith("<|im_start|>assistant\n")
    assert not without.endswith("<|im_start|>assistant\n")


def test_record_then_check_round_trip(run_cli, write_fixture, tmp_path):
    write_fixture("convo.json")
    goldens = tmp_path / "goldens"
    code, out, _ = run_cli(
        "record", "-t", "chatml", "-f", str(tmp_path / "convo.json"),
        "-g", str(goldens),
    )
    assert code == 0
    assert "written" in out
    code, out, _ = run_cli(
        "check", "-t", "chatml", "-f", str(tmp_path / "convo.json"),
        "-g", str(goldens),
    )
    assert code == 0
    assert "all byte-identical" in out


def test_check_exits_1_when_goldens_were_never_recorded(run_cli, write_fixture, tmp_path):
    fixture = write_fixture("convo.json")
    goldens = tmp_path / "goldens"
    run_cli("record", "-t", "chatml", "-f", str(fixture), "-g", str(goldens))
    # Checking a different template finds no goldens under its label.
    code, out, _ = run_cli(
        "check", "-t", "zephyr", "-f", str(fixture), "-g", str(goldens)
    )
    assert code == 1
    assert "MISSING" in out


def test_check_reports_mismatch_when_golden_drifts(run_cli, write_fixture, tmp_path):
    fixture = write_fixture("convo.json")
    goldens = tmp_path / "goldens"
    run_cli("record", "-t", "chatml", "-f", str(fixture), "-g", str(goldens))
    golden_file = next(goldens.glob("*.golden.txt"))
    golden_file.write_text(
        golden_file.read_text(encoding="utf-8").replace("terse", "verbose"),
        encoding="utf-8",
    )
    code, out, _ = run_cli(
        "check", "-t", "chatml", "-f", str(fixture), "-g", str(goldens)
    )
    assert code == 1
    assert "MISMATCH  convo" in out
    assert "-You are verbose.<|im_end|>\\n" in out
    assert "+You are terse.<|im_end|>\\n" in out


def test_diff_identical_exits_0_and_different_exits_1(run_cli, write_fixture):
    path = write_fixture("convo.json")
    code, out, _ = run_cli("diff", "chatml", "chatml", "-f", str(path))
    assert code == 0
    assert out.startswith("identical:")
    code, out, _ = run_cli("diff", "chatml", "zephyr", "-f", str(path))
    assert code == 1
    assert "--- chatml" in out
    assert "+++ zephyr" in out


def test_presets_lists_all_builtins(run_cli):
    code, out, _ = run_cli("presets")
    assert code == 0
    for name in ("chatml", "inst", "zephyr", "alpaca", "plain"):
        assert name in out


def test_errors_exit_2_with_message_on_stderr(run_cli, write_fixture, tmp_path):
    path = write_fixture("convo.json")
    code, out, err = run_cli("render", "-t", "nope", "-f", str(path))
    assert code == 2 and out == ""
    assert "neither a built-in preset" in err
    template = tmp_path / "broken.jinja"
    template.write_text("ok\n{{ messages | frobnicate }}", encoding="utf-8")
    code, _, err = run_cli("render", "-t", str(template), "-f", str(path))
    assert code == 2
    assert "broken.jinja:2:" in err


def test_broken_pipe_exits_141_not_1(monkeypatch):
    # `chatstencil ... | head` must not report exit 1: scripts gating on
    # `check` would read that as drift. 141 (128 + SIGPIPE) is the shell
    # convention for "the reader went away".
    class ClosedPipe:
        def write(self, _text):
            raise BrokenPipeError()

        def flush(self):
            pass

        def fileno(self):
            raise OSError("no underlying file descriptor")

    monkeypatch.setattr(sys, "stdout", ClosedPipe())
    assert main(["presets"]) == 141


def test_version_matches_the_package(run_cli, capsys):
    with pytest.raises(SystemExit) as excinfo:
        run_cli("--version")
    assert excinfo.value.code == 0
    assert capsys.readouterr().out.strip() == f"chatstencil {chatstencil.__version__}"
