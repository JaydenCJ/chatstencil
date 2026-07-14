# Examples

A ready-made golden workflow you can run straight from a checkout
(`PYTHONPATH=src python3 -m chatstencil ...` or just `chatstencil` after
`pip install -e .`):

- `fixtures/` — three message fixtures: a plain system+user exchange
  (`smalltalk`), a two-exchange conversation (`multi-turn`), and a
  conversation without a system message (`no-system`), which is the branch
  templates most often get wrong.
- `templates/support-bot.jinja` — a custom ChatML-flavored template with
  house rules (single leading system message enforced via
  `raise_exception`, trimmed content, whitespace-control markers).
- `goldens/` — recorded goldens for the `chatml` preset and for
  `support-bot.jinja` against all three fixtures. They are committed so the
  check below passes on a fresh clone.

Verify the committed goldens are still byte-identical:

```bash
chatstencil check -t chatml -f examples/fixtures -g examples/goldens
chatstencil check -t examples/templates/support-bot.jinja \
    -f examples/fixtures -g examples/goldens
```

Now break something on purpose — edit `templates/support-bot.jinja` (delete
the `| trim`, or a `\n` inside a text run) and re-run the second command:
the exit code flips to 1 and the diff shows the exact bytes that changed.

To accept an intentional template change, re-record:

```bash
chatstencil record -t examples/templates/support-bot.jinja \
    -f examples/fixtures -g examples/goldens
```

Compare two templates on the same conversation:

```bash
chatstencil diff chatml examples/templates/support-bot.jinja \
    -f examples/fixtures/smalltalk.json
```

The tests in `tests/test_examples.py` run these same checks, so the examples
can never silently rot.
