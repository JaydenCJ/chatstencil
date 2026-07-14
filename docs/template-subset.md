# The chatstencil template dialect

chatstencil implements the subset of Jinja that published chat templates
actually use, on the Python standard library alone. This page is the
authoritative list of what is supported in 0.1.0. Anything not listed here
is rejected with a `TemplateSyntaxError` or `TemplateRuntimeError` that
names the construct — never silently ignored.

## Delimiters

| Syntax | Meaning |
|---|---|
| `{{ expression }}` | Output the expression's text |
| `{% statement %}` | A statement tag (`for`, `if`, `elif`, `else`, `set`, and the matching `end*`) |
| `{# comment #}` | Dropped entirely |
| `{{-` `-}}` `{%-` `-%}` `{#-` `-#}` | Whitespace control: `-` on the open trims text to the left, on the close trims to the right (identical to Jinja) |

All text outside delimiters is emitted **byte-for-byte** — tabs, trailing
spaces, and blank lines survive rendering untouched.

## Statements

- `{% for name in expr %} ... {% endfor %}` — iterates lists, tuples,
  strings (characters), and mappings (keys). Inside the body, `loop`
  provides `index`, `index0`, `first`, `last`, `length`, `revindex`,
  `revindex0`. Tuple unpacking (`for k, v in ...`) is not supported.
- `{% if expr %} ... {% elif expr %} ... {% else %} ... {% endif %}`
- `{% set name = expr %}` — writes to the **innermost** scope, so
  assignments inside a loop do not leak out (the Jinja behavior that makes
  `namespace()` necessary).
- `{% set ns.attr = expr %}` — mutates a `namespace()` object; anything
  else as the target is an error.

## Expressions

Operators, loosest to tightest binding:

`x if cond else y` (else optional) → `or` → `and` → `not` → comparisons
(`==` `!=` `<` `<=` `>` `>=` `in` `not in` `is` `is not`) → `~` (concat,
coerces to text) → `+ -` → `* / %` → unary `-` → postfix
(`.attr`, `[item]`, `(call)`, `| filter`).

Literals: single/double-quoted strings with `\n \t \r \\ \' \"` escapes,
integers, floats, `true/false/none` (both capitalizations), and
`[list, literals]`. Dict literals are not supported.

Failed subscripts (`messages[0]` on an empty list, missing dict keys)
resolve to an **undefined** value — falsy, renders as `""`, detectable with
`is defined` — matching how templates probe conversations. Reading an
attribute *of* an undefined value is a loud error.

## Filters

`trim upper lower title capitalize length count first last join replace
default d string int float list reverse tojson indent abs safe`

`tojson` sorts keys and keeps non-ASCII characters, so output is
deterministic and diff-friendly. `safe` is the identity (chatstencil never
HTML-escapes). Unknown filters raise an error listing the supported names.

## Tests

`defined undefined none string number boolean mapping sequence iterable
odd even`

## Callables (the whole sandbox surface)

Global functions: `raise_exception(message)` (abort rendering — how real
templates reject unsupported role sequences), `namespace(**kwargs)`, and
`range(...)` (capped at 10 000 elements).

Methods, per receiver type — nothing outside this list is reachable, so a
template file cannot escape into the interpreter:

| Type | Allowed methods |
|---|---|
| `str` | `strip lstrip rstrip upper lower title capitalize startswith endswith replace split find join removeprefix removesuffix` |
| `dict` | `get keys values items` |
| `list` | `index count` |

## Known differences from full Jinja

- No macros, includes, inheritance, `{% raw %}`, or line statements.
- No `selectattr` / `map` / `groupby` filter family.
- No dict literals or tuple unpacking in `for`.
- `loop.cycle` and `loop.previtem/nextitem` are not provided.

These are deliberate: none of them appear in the chat templates this tool
targets, and every omission fails loudly rather than rendering wrong bytes.
If a real model's template needs a construct outside this list, that is a
bug worth an issue.
