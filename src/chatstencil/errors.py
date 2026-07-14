"""Exception hierarchy for chatstencil.

Every error raised on purpose by this package derives from
:class:`ChatStencilError`, so callers (and the CLI) can catch one type and
present a clean message instead of a traceback.
"""

from __future__ import annotations


class ChatStencilError(Exception):
    """Base class for all chatstencil errors."""


class TemplateError(ChatStencilError):
    """Base class for template compilation and rendering errors.

    Carries the template name and 1-based line number so error messages can
    point at the exact spot in the template source.
    """

    def __init__(self, message: str, name: str = "<template>", line: int = 0):
        self.message = message
        self.name = name
        self.line = line
        super().__init__(str(self))

    def __str__(self) -> str:
        if self.line:
            return f"{self.name}:{self.line}: {self.message}"
        return f"{self.name}: {self.message}"


class TemplateSyntaxError(TemplateError):
    """The template source could not be tokenized or parsed."""


class TemplateRuntimeError(TemplateError):
    """The template compiled but failed while rendering.

    Also raised by the template-level ``raise_exception(...)`` helper that
    real chat templates use to reject unsupported conversations.
    """


class FixtureError(ChatStencilError):
    """A message fixture file is missing, unreadable, or malformed."""
