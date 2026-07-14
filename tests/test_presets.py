"""Golden assertions for every built-in preset.

These are exact-string tests on purpose: the presets are the reference
renderings users compare their own templates against, so a one-byte change
here is a breaking change.
"""

import pytest

from chatstencil import PRESETS, load_template, render_chat
from chatstencil.errors import TemplateRuntimeError


def preset_render(name, messages, gen=True, **overrides):
    loaded = load_template(name)
    variables = dict(loaded.defaults)
    variables.update(overrides)
    return loaded.template.render(
        messages=messages, add_generation_prompt=gen, **variables
    )


def test_chatml_exact_string(messages):
    assert preset_render("chatml", messages) == (
        "<|im_start|>system\nYou are terse.<|im_end|>\n"
        "<|im_start|>user\nhi<|im_end|>\n"
        "<|im_start|>assistant\nhello<|im_end|>\n"
        "<|im_start|>user\nbye<|im_end|>\n"
        "<|im_start|>assistant\n"
    )


def test_inst_folds_system_into_first_user_turn_only(messages):
    assert preset_render("inst", messages) == (
        "<s>[INST] You are terse.\n\nhi [/INST] hello</s>[INST] bye [/INST]"
    )
    assert preset_render("inst", [{"role": "user", "content": "hi"}]) == (
        "<s>[INST] hi [/INST]"
    )


def test_inst_rejects_unknown_roles():
    msgs = [{"role": "tool", "content": "{}"}]
    with pytest.raises(TemplateRuntimeError, match="got: tool"):
        preset_render("inst", msgs)


def test_zephyr_default_eos_token_and_override(messages):
    assert preset_render("zephyr", messages[:2]) == (
        "<|system|>\nYou are terse.</s>\n<|user|>\nhi</s>\n<|assistant|>\n"
    )
    out = preset_render("zephyr", messages[:2], eos_token="<END>")
    assert "</s>" not in out
    assert out.count("<END>") == 2


def test_alpaca_exact_string(messages):
    assert preset_render("alpaca", messages) == (
        "You are terse.\n\n"
        "### Instruction:\nhi\n\n"
        "### Response:\nhello\n\n"
        "### Instruction:\nbye\n\n"
        "### Response:\n"
    )


def test_plain_preset_and_generation_prompt_off(messages):
    assert preset_render("plain", messages, gen=False) == (
        "system: You are terse.\nuser: hi\nassistant: hello\nuser: bye\n"
    )
    assert preset_render("plain", messages, gen=True).endswith("assistant:")


def test_every_preset_compiles_and_renders_nonempty(messages):
    for name in PRESETS:
        out = preset_render(name, messages)
        assert out, f"preset {name} rendered an empty prompt"


def test_render_chat_defaults_special_tokens_to_empty(messages):
    # render_chat on a raw source has no preset defaults: bos/eos are ''.
    out = render_chat(PRESETS["inst"].source, messages[:2])
    assert out == "[INST] You are terse.\n\nhi [/INST]"
