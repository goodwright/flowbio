# Contract: CLI Conventions (shared)

These conventions apply to every `flowbio` command. Per-command contracts in
this directory only restate options unique to that command.

## Command shape

```
flowbio <resource> <verb> [options]
flowbio --version
flowbio [--help | <resource> --help | <resource> <verb> --help]
```

- Resources: `data`, `samples`. Verbs are listed in each command contract.
- No resource, no verb, or an unknown resource/verb → help shown, exit `2`
  (FR-003).

## Global options (accepted before *and* after the verb — FR-004)

| Option | Env var | Effect |
|--------|---------|--------|
| `--json` | — | Emit one JSON document on stdout; nothing else on stdout. |
| `--no-progress` | — | Disable progress output (otherwise on stderr). |
| `--token TOKEN` | `FLOW_API_TOKEN` | Use this token directly. |
| `--token-file PATH` | `FLOW_TOKEN_FILE` | Read token from this file. |
| `--base-url URL` | `FLOW_API_URL` | Override the Flow API base URL. |
| `--login` | — | Force interactive username/password login. |
| `--username NAME` | — | Username for login (password is always prompted). |

`flowbio --json samples upload …` ≡ `flowbio samples upload … --json`.

## Authentication resolution (FR-006…FR-013)

Precedence: `--login` → `--token`/`FLOW_API_TOKEN` →
`--token-file`/`FLOW_TOKEN_FILE` → default file `~/.config/flow/api-token` →
username/password prompt. For token & base-URL: flag > env > default.

- Password is **only** prompted interactively (`getpass`); never a flag/env.
- Named token file missing/empty → exit `2`.
- `--token` with `--login` → exit `2`.
- Prompt needed but non-interactive stdin → exit `2`, fail fast with an
  actionable message.

## Output modes (FR-035…FR-037)

- **Human (default)**: concise result lines on stdout; advisories/progress/errors
  on stderr.
- **`--json`**: exactly one JSON document on stdout; on error, a JSON document on
  stderr carrying `message` and (where applicable) a status code.

## Exit codes (FR-038)

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | API/runtime error (incl. a batch with any failed upload) |
| `2` | Usage/configuration/input error (incl. batch pre-flight failure, non-CSV sheet) |
| `3` | Authentication failed |
| `4` | Not found |
| `5` | Bad request / validation error |

Mapping from library exceptions: `AuthenticationError→3`, `NotFoundError→4`,
`BadRequestError`/`AnnotationValidationError→5`, other `FlowApiError→1`.

## Server is source of truth

The CLI does **not** pre-validate `--sample-type` or `--data-type` against the
server; the value is sent as-is and a server rejection surfaces as exit `5`.
