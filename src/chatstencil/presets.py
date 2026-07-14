"""Built-in template presets and template loading.

Each preset is a well-known prompt wire format, written in the chatstencil
dialect with byte-exact output.  Presets carry their own default special
tokens (e.g. the ``inst`` family assumes ``<s>``/``</s>``); fixtures and the
CLI can override them.

``load_template`` resolves a template reference: a preset name first, then a
path to a template file on disk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict

from .errors import ChatStencilError
from .template import Template


@dataclass(frozen=True)
class Preset:
    name: str
    description: str
    source: str
    defaults: Dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class LoadedTemplate:
    """A resolved template plus its default variables and a short label."""

    template: Template
    defaults: Dict[str, str]
    label: str


_CHATML = Preset(
    name="chatml",
    description="<|im_start|>role ... <|im_end|> turn markers",
    source=(
        "{% for message in messages %}"
        "<|im_start|>{{ message.role }}\n"
        "{{ message.content }}<|im_end|>\n"
        "{% endfor %}"
        "{% if add_generation_prompt %}"
        "<|im_start|>assistant\n"
        "{% endif %}"
    ),
)

_INST = Preset(
    name="inst",
    description="[INST] ... [/INST] bracketed turns, system folded into first user turn",
    source=(
        "{{ bos_token }}"
        "{% set ns = namespace(sys='') %}"
        "{% for message in messages %}"
        "{% if message.role == 'system' %}"
        "{% set ns.sys = message.content %}"
        "{% elif message.role == 'user' %}"
        "[INST] {% if ns.sys %}{{ ns.sys }}\n\n{% set ns.sys = '' %}{% endif %}"
        "{{ message.content }} [/INST]"
        "{% elif message.role == 'assistant' %}"
        " {{ message.content }}{{ eos_token }}"
        "{% else %}"
        "{{ raise_exception('inst supports system, user and assistant roles, "
        "got: ' ~ message.role) }}"
        "{% endif %}"
        "{% endfor %}"
    ),
    defaults={"bos_token": "<s>", "eos_token": "</s>"},
)

_ZEPHYR = Preset(
    name="zephyr",
    description="<|role|> headers with a sentence-end token after each turn",
    source=(
        "{% for message in messages %}"
        "<|{{ message.role }}|>\n"
        "{{ message.content }}{{ eos_token }}\n"
        "{% endfor %}"
        "{% if add_generation_prompt %}"
        "<|assistant|>\n"
        "{% endif %}"
    ),
    defaults={"eos_token": "</s>"},
)

_ALPACA = Preset(
    name="alpaca",
    description="### Instruction: / ### Response: sections, instruction-tuned style",
    source=(
        "{% for message in messages %}"
        "{% if message.role == 'system' %}"
        "{{ message.content }}\n\n"
        "{% elif message.role == 'user' %}"
        "### Instruction:\n{{ message.content }}\n\n"
        "{% elif message.role == 'assistant' %}"
        "### Response:\n{{ message.content }}\n\n"
        "{% else %}"
        "{{ raise_exception('alpaca supports system, user and assistant roles, "
        "got: ' ~ message.role) }}"
        "{% endif %}"
        "{% endfor %}"
        "{% if add_generation_prompt %}### Response:\n{% endif %}"
    ),
)

_PLAIN = Preset(
    name="plain",
    description="role: content lines; the null template for baselining diffs",
    source=(
        "{% for message in messages %}"
        "{{ message.role }}: {{ message.content }}\n"
        "{% endfor %}"
        "{% if add_generation_prompt %}assistant:{% endif %}"
    ),
)

PRESETS: Dict[str, Preset] = {
    p.name: p for p in (_CHATML, _INST, _ZEPHYR, _ALPACA, _PLAIN)
}


def load_template(ref: str) -> LoadedTemplate:
    """Resolve *ref* as a preset name, else as a template file path."""
    preset = PRESETS.get(ref)
    if preset is not None:
        return LoadedTemplate(
            template=Template(preset.source, name=f"preset:{ref}"),
            defaults=dict(preset.defaults),
            label=ref,
        )
    path = Path(ref)
    if path.is_file():
        source = path.read_text(encoding="utf-8")
        return LoadedTemplate(
            template=Template(source, name=str(path)),
            defaults={},
            label=path.stem,
        )
    known = ", ".join(sorted(PRESETS))
    raise ChatStencilError(
        f"template '{ref}' is neither a built-in preset ({known}) "
        "nor an existing file"
    )
