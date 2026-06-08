# flowbio — contributor & agent guide

Repo-specific conventions that complement the project constitution
(`.specify/memory/constitution.md`) and any global guidance. Keep these in mind
on every change.

## Typing

Use strict, explicit typing.

- Prefer **named types** (`typing.NewType`) for primitive identifiers and tokens,
  and `pathlib.Path` for filesystem paths, over a bare `str`.
- Avoid `object` in signatures — type the actual shape (e.g. a `JsonValue`
  alias for JSON-serialisable values).
- Returned values are frozen Pydantic models; inputs are plain dicts.

## Testing

Test **public functionality**, not private internals.

- It is fine to test a public function that lives in a `_`-prefixed module, but
  as a rule do **not** reach in and test `_`-prefixed (private) functions —
  exercise them through the public function (or CLI) that uses them. The
  `run_cli` fixture is one way to do this, not the only one.
- Test-first: write a failing test, confirm red, implement, confirm green.

## CLI (`flowbio/cli`)

- User docs (`docs/cli.md`) should not duplicate `--help` output. Keep the docs
  to concepts (authentication precedence, output modes, the exit-code contract)
  plus a worked example per command, and let `--help` carry the exhaustive
  per-option list.
