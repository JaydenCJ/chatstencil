"""The public :class:`Template` object and rendering helpers.

A template is compiled once (tokenize → parse) and can be rendered many
times.  ``render_chat`` is the one-call convenience API; ``render_fixture``
is what the CLI and the golden workflow use, and defines the variable
precedence: engine defaults < template defaults < fixture vars < caller vars.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from .errors import TemplateRuntimeError
from .evaluate import Evaluator
from .lexer import tokenize
from .parser import Parser

#: Variables every render sees unless overridden.  Chat templates written for
#: tokenizer runtimes reference special tokens; empty defaults keep renders
#: honest (a missing token shows up as an exact-string diff, not a crash).
ENGINE_DEFAULTS: Dict[str, Any] = {
    "bos_token": "",
    "eos_token": "",
    "unk_token": "",
    "pad_token": "",
    "add_generation_prompt": False,
}


class Template:
    """A compiled chat template."""

    def __init__(self, source: str, name: str = "<template>"):
        self.source = source
        self.name = name
        self.body = Parser(tokenize(source, name), name).parse()

    def render(self, **variables: Any) -> str:
        """Render with *variables*; engine defaults fill any gaps."""
        merged = dict(ENGINE_DEFAULTS)
        merged.update(variables)
        return Evaluator(self.name, merged).render(self.body)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"Template(name={self.name!r})"


def render_chat(
    source: str,
    messages: List[Dict[str, Any]],
    add_generation_prompt: bool = True,
    name: str = "<template>",
    **variables: Any,
) -> str:
    """Compile *source* and render it against *messages* in one call."""
    template = Template(source, name)
    return template.render(
        messages=messages,
        add_generation_prompt=add_generation_prompt,
        **variables,
    )


def render_fixture(
    template: Template,
    fixture: Any,
    defaults: Optional[Dict[str, Any]] = None,
    extra_vars: Optional[Dict[str, Any]] = None,
    generation_prompt: Optional[bool] = None,
) -> str:
    """Render *fixture* (a :class:`chatstencil.fixtures.Fixture`).

    Variable precedence, lowest to highest: engine defaults, template
    *defaults* (e.g. a preset's special tokens), the fixture's ``vars``,
    then *extra_vars* from the caller (CLI ``--var``).  *generation_prompt*
    overrides the fixture's ``add_generation_prompt`` when not ``None``.
    """
    variables: Dict[str, Any] = {}
    variables.update(defaults or {})
    variables.update(fixture.vars)
    variables.update(extra_vars or {})
    gen = fixture.add_generation_prompt if generation_prompt is None else generation_prompt
    try:
        return template.render(
            messages=fixture.messages,
            add_generation_prompt=gen,
            **variables,
        )
    except TemplateRuntimeError as exc:
        raise TemplateRuntimeError(
            f"{exc.message} (while rendering fixture '{fixture.name}')",
            exc.name,
            exc.line,
        ) from None
