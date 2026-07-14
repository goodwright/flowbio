# `flowbio api get` — read-only API passthrough

## Problem

The `flow-ai` skill issues Flow reads with `curl`, attaching the token via a
command substitution:

```bash
curl -s -A "flow-ai/0.8.0" \
  -H "Authorization: Bearer $(< ~/.config/flow/api-token)" \
  --get ".../pipelines"
```

Claude Code will not auto-approve a Bash command that contains command
substitution (`$(< …)`), because the substitution is unanalyzable. As a result
every read prompts for permission, regardless of any `curl` allowlist entry. The
dynamic URL and per-call flags make prefix-allowlisting fragile on top of that.

## Goal

Provide a single, allowlistable CLI command for authenticated GET reads so the
skill can run `flowbio api get …` — a static-prefix command with no embedded
substitution — and the user can approve it once with `Bash(flowbio api get:*)`.

This also consolidates token handling in the CLI (which already owns it for
uploads), removes the fragile `curl` + shell layer, and keeps the raw token out
of argv and the transcript.

## Command

```
flowbio api get <path> [--param KEY=VALUE ...]
```

A new `api` resource sits beside the existing `data` and `samples` resources,
with a single `get` verb. It inherits all global options (`--token`,
`--token-file`, `--base-url`, `--json`, `--login`, `--username`, …).

### Path

`<path>` is relative to the configured base URL, joined the same way
`HttpTransport._url` already joins it (`{base_url}/{path.lstrip('/')}`, leading
slash optional):

- `flowbio api get /samples/search` → `GET <base>/samples/search`
- `flowbio api get samples/types` → same host, identical result.

Because the path is always joined onto the configured base URL, the command can
only ever reach paths under the configured Flow host — it cannot be steered to
an arbitrary URL.

### Query parameters

Query values are supplied **only** via `--param KEY=VALUE`, which the CLI
URL-encodes into the query string. This removes the URL-encoding foot-guns the
skill's rules warn about. `<path>` carries the path only: a `?` in `<path>` is
rejected with a usage error that points at `--param`, so encoding can never be
bypassed.

## Behaviour

- **Credentials.** Resolved via the existing `resolve_credentials` precedence.
  The default token file (`~/.config/flow/api-token`) needs no flags — this is
  what removes the permission prompts.
- **Request.** Issued through a new **public `Client` read primitive** that
  wraps `HttpTransport.get_bytes`, so the CLI handler is tested against a public
  API rather than reaching into `client._transport`.
- **Success.** Exit `0`; the raw response body is written verbatim to stdout
  (bytes). The skill's existing `jq` pipelines and output discipline transfer
  unchanged. `--json` does **not** reshape success output — the body is already
  the API's JSON.
- **Failure.** `FlowApiError` propagates to the existing `_dispatch` handler,
  which renders `{"message": …, "status_code": …}` to stderr in `--json` mode
  and maps the status to the existing exit code (400→5, 401→3, 404→4, others→1).
  No new exit code is introduced. This is the same failure contract the skill
  already knows from uploads.

## Safety

- **GET-only by construction** — there is no method argument, so the command
  cannot mutate remote state.
- **Host-constrained** — the path is always joined onto the configured base URL.
- The skill keeps its endpoint allowlist in prose; the CLI stays a
  generic-but-read-only transport. The user allowlists `Bash(flowbio api get:*)`
  once.

## Testing

Test-first, exercised through the public CLI (the `run_cli` fixture) per the
repo's testing rule:

- `--param KEY=VALUE` is URL-encoded into the query string.
- Leading-slash and no-leading-slash paths behave identically.
- A `?` in `<path>` is rejected with a usage error.
- On success, the raw response body is passed through to stdout unchanged.
- On error, the status maps to the correct exit code and the stderr envelope
  carries `message` and `status_code` in `--json` mode.
- Credential precedence holds (default token file vs `--token`).

Plus a unit test for the new public `Client` read primitive.

## Out of scope

- POST / mutations. Running a pipeline stays a `curl`-with-confirmation flow in
  the skill for now.
- Typed per-endpoint commands (`flowbio pipelines list`, …).
- The skill rewrite itself — a separate follow-up once this command ships.
