"""chatstencil — render chat templates against message fixtures and
golden-test the exact prompt strings.

Public API:

- :class:`Template` / :func:`render_chat` — compile and render templates
- :func:`load_template` / :data:`PRESETS` — resolve presets or template files
- :func:`load_fixture` / :func:`discover_fixtures` — message fixtures
- :func:`render_fixture` — render a fixture with full variable precedence
- :func:`record_goldens` / :func:`check_goldens` / :func:`diff_strings` —
  the golden-testing workflow
- the exception hierarchy under :class:`ChatStencilError`
"""

from .errors import (
    ChatStencilError,
    FixtureError,
    TemplateError,
    TemplateRuntimeError,
    TemplateSyntaxError,
)
from .fixtures import Fixture, discover_fixtures, load_fixture
from .golden import check_goldens, diff_strings, escape_lines, record_goldens
from .presets import PRESETS, LoadedTemplate, Preset, load_template
from .runtime import Undefined
from .template import Template, render_chat, render_fixture

__version__ = "0.1.0"

__all__ = [
    "__version__",
    "ChatStencilError",
    "FixtureError",
    "TemplateError",
    "TemplateRuntimeError",
    "TemplateSyntaxError",
    "Fixture",
    "discover_fixtures",
    "load_fixture",
    "check_goldens",
    "diff_strings",
    "escape_lines",
    "record_goldens",
    "PRESETS",
    "LoadedTemplate",
    "Preset",
    "load_template",
    "Undefined",
    "Template",
    "render_chat",
    "render_fixture",
]
