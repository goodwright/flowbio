# `flowbio api get` Read-Only Passthrough Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a read-only `flowbio api get <path> [--param KEY=VALUE ...]` CLI command that resolves credentials itself and writes the raw API response body to stdout, so the flow-ai skill can replace per-call `curl` (which Claude Code cannot auto-approve) with a single allowlistable command.

**Architecture:** A new `api` resource sits beside `data`/`samples` in the parser tree with one `get` verb. Its handler parses `--param` pairs, rejects a `?` in the path, and calls a new public `Client.get_raw` primitive that wraps a new `HttpTransport.get_text`. The raw response body is written verbatim to stdout via a new `Output.emit_raw`; errors flow through the existing `_dispatch` `FlowApiError` handler unchanged (same status→exit-code mapping and `--json` stderr envelope the uploads already use).

**Tech Stack:** Python 3.11+, argparse, httpx, respx + pytest (in-process `run_cli` fixture).

## Global Constraints

- Python 3.11+ (minimum supported version).
- Strict, explicit typing: named types for identifiers/paths, no bare `object`; returned library values are frozen Pydantic models, inputs are plain dicts.
- Test-first (red → green → refactor). Test public functionality through the public CLI (`run_cli`) or public library API — never reach into `_`-prefixed functions directly.
- Comments only for a non-obvious *why*; no strategy/flow narration.
- Conventional-commit messages; no plan/spec IDs in code, comments, or commits.
- Commit message footer: `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

### Task 1: Public GET-raw read primitive on transport and client

**Files:**
- Modify: `flowbio/v2/_transport.py` (add `get_text` next to `get`/`get_bytes`, ~line 154)
- Modify: `flowbio/v2/client.py` (add `get_raw` public method on `Client`)
- Test: `tests/unit/v2/test_transport.py`, `tests/unit/v2/test_client.py`

**Interfaces:**
- Consumes: existing `HttpTransport._request`, `HttpTransport._raise_for_error`, `HttpTransport._url`; `Client._transport`.
- Produces:
  - `HttpTransport.get_text(self, path: str, params: list[tuple[str, str]] | None = None) -> str` — sends GET, raises `FlowApiError` on non-2xx, returns `response.text`.
  - `Client.get_raw(self, path: str, params: list[tuple[str, str]] | None = None) -> str` — delegates to `get_text`; returns the raw response body text.

- [ ] **Step 1: Write the failing transport test**

Add to `tests/unit/v2/test_transport.py`:

```python
class TestTransportGetText:

    @respx.mock
    def test_returns_raw_response_body_verbatim(self) -> None:
        body = '{"count": 2, "pipelines": [1, 2]}'
        respx.get(f"{DEFAULT_BASE_URL}/pipelines").mock(
            return_value=httpx.Response(HTTPStatus.OK, text=body),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        assert transport.get_text("/pipelines") == body

    @respx.mock
    def test_encodes_params_into_query_string(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        transport.get_text("/samples/search", params=[("name", "rna seq")])

        assert route.calls[0].request.url.params.get("name") == "rna seq"

    @respx.mock
    def test_raises_flow_api_error_on_non_success(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/nope").mock(
            return_value=httpx.Response(
                HTTPStatus.NOT_FOUND, json={"error": "missing"},
            ),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(NotFoundError):
            transport.get_text("/nope")
```

- [ ] **Step 2: Run the transport test to verify it fails**

Run: `uv run pytest tests/unit/v2/test_transport.py::TestTransportGetText -v`
Expected: FAIL with `AttributeError: 'HttpTransport' object has no attribute 'get_text'`.

- [ ] **Step 3: Implement `get_text` on the transport**

In `flowbio/v2/_transport.py`, add immediately after `get_bytes` (after line ~166):

```python
    def get_text(
        self, path: str, params: list[tuple[str, str]] | None = None,
    ) -> str:
        """Send a GET request and return the raw response body as text.

        Unlike :meth:`get`, the body is returned undecoded from JSON so
        callers can pass it through verbatim.

        :param path: The API path to request.
        :param params: Optional query parameters, as key/value pairs so a
            key may repeat (e.g. multiple ``sample_types`` filters).
        :returns: The response body text.
        :raises FlowApiError: If the API returns a non-success status code.
        """
        response = self._request(HTTPMethod.GET, self._url(path), params=params)
        self._raise_for_error(response)
        return response.text
```

- [ ] **Step 4: Run the transport test to verify it passes**

Run: `uv run pytest tests/unit/v2/test_transport.py::TestTransportGetText -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing client test**

Add to `tests/unit/v2/test_client.py`:

```python
class TestClientGetRaw:

    @respx.mock
    def test_returns_raw_body_for_path(self) -> None:
        body = '{"count": 0, "samples": []}'
        respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(200, text=body),
        )

        assert Client().get_raw("/samples/search") == body

    @respx.mock
    def test_forwards_params_as_repeatable_pairs(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(200, text="{}"),
        )
        params = [("sample_types", "rna"), ("sample_types", "atac")]

        Client().get_raw("/samples/search", params=params)

        assert sorted(route.calls[0].request.url.params.multi_items()) == sorted(params)
```

- [ ] **Step 6: Run the client test to verify it fails**

Run: `uv run pytest tests/unit/v2/test_client.py::TestClientGetRaw -v`
Expected: FAIL with `AttributeError: 'Client' object has no attribute 'get_raw'`.

- [ ] **Step 7: Implement `get_raw` on the client**

In `flowbio/v2/client.py`, add a method on `Client` (after `log_in`):

```python
    def get_raw(
        self, path: str, params: list[tuple[str, str]] | None = None,
    ) -> str:
        """Issue a GET to an arbitrary API path and return the raw body text.

        A low-level read escape hatch used by the CLI's ``api get`` command.
        The path is joined onto the configured base URL, so only paths on
        that host are reachable.

        :param path: API path relative to the base URL (leading slash optional).
        :param params: Optional query parameters as key/value pairs.
        :returns: The raw response body text.
        :raises FlowApiError: If the API returns a non-success status code.
        """
        return self._transport.get_text(path, params=params)
```

- [ ] **Step 8: Run the client test to verify it passes**

Run: `uv run pytest tests/unit/v2/test_client.py::TestClientGetRaw -v`
Expected: PASS (2 tests).

- [ ] **Step 9: Commit**

```bash
git add flowbio/v2/_transport.py flowbio/v2/client.py tests/unit/v2/test_transport.py tests/unit/v2/test_client.py
git commit -m "feat(v2): add raw GET read primitive to transport and client

The CLI's api-get passthrough needs to return an API response body
verbatim. Add HttpTransport.get_text and Client.get_raw alongside the
existing typed getters, returning the undecoded body text.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: `Output.emit_raw` for verbatim stdout

**Files:**
- Modify: `flowbio/cli/_output.py` (add `emit_raw` on `Output`)
- Test: `tests/unit/cli/test_output.py`

**Interfaces:**
- Consumes: `Output.stdout`.
- Produces: `Output.emit_raw(self, body: str) -> None` — writes `body` to stdout verbatim (no newline added, no JSON wrapping), regardless of `json_mode`.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/cli/test_output.py`:

```python
class TestEmitRaw:

    def test_writes_body_verbatim_without_added_newline(self) -> None:
        body = '{"count": 1}'
        stdout, stderr = io.StringIO(), io.StringIO()
        output = Output(json_mode=False, stdout=stdout, stderr=stderr)

        output.emit_raw(body)

        assert stdout.getvalue() == body

    def test_writes_verbatim_in_json_mode_too(self) -> None:
        body = '{"count": 1}'
        stdout, stderr = io.StringIO(), io.StringIO()
        output = Output(json_mode=True, stdout=stdout, stderr=stderr)

        output.emit_raw(body)

        assert stdout.getvalue() == body
```

Ensure `io` is imported at the top of `tests/unit/cli/test_output.py` (add `import io` if absent) and `Output` is imported from `flowbio.cli._output`.

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run pytest tests/unit/cli/test_output.py::TestEmitRaw -v`
Expected: FAIL with `AttributeError: 'Output' object has no attribute 'emit_raw'`.

- [ ] **Step 3: Implement `emit_raw`**

In `flowbio/cli/_output.py`, add a method on `Output` (after `emit_result`):

```python
    def emit_raw(self, body: str) -> None:
        """Write a response body to stdout verbatim.

        Used for passthrough output where the body is already the exact
        bytes to surface: no newline is appended and ``json_mode`` does not
        reshape it.

        :param body: The text to write to stdout unchanged.
        """
        self.stdout.write(body)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run pytest tests/unit/cli/test_output.py::TestEmitRaw -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add flowbio/cli/_output.py tests/unit/cli/test_output.py
git commit -m "feat(cli): add Output.emit_raw for verbatim stdout

The api-get passthrough must surface the response body byte-for-byte so
the caller can pipe it through jq. Add emit_raw, which writes to stdout
unchanged in both human and --json modes.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: `flowbio api get` command (parser, handler, wiring)

**Files:**
- Create: `flowbio/cli/_api.py`
- Modify: `flowbio/cli/_parser.py` (import and register the `api` resource)
- Test: `tests/unit/cli/test_api.py`

**Interfaces:**
- Consumes: `Client.get_raw` (Task 1), `Output.emit_raw` (Task 2), `CliUsageError` and `ExitCode` from `flowbio.cli._exit_codes`.
- Produces:
  - `flowbio.cli._api.register(resource: argparse.ArgumentParser, global_parent: argparse.ArgumentParser) -> None` — registers the `get` verb with a positional `path` (dest `path`) and repeatable `--param` (dest `param`, `action="append"`).
  - Handler `_get_command(args, client, output) -> ExitCode` set as the verb's `handler`.

- [ ] **Step 1: Write the failing command tests**

Create `tests/unit/cli/test_api.py`:

```python
import json
from http import HTTPStatus

import httpx
import respx

from tests.unit.cli.conftest import DEFAULT_BASE_URL

TOKEN = "test.token"


class TestApiGet:

    @respx.mock
    def test_writes_raw_body_to_stdout_verbatim(self, run_cli) -> None:
        body = '{"count": 2, "pipelines": ["a", "b"]}'
        respx.get(f"{DEFAULT_BASE_URL}/pipelines").mock(
            return_value=httpx.Response(HTTPStatus.OK, text=body),
        )

        result = run_cli("api", "get", "/pipelines", "--token", TOKEN)

        assert result.exit_code == 0
        assert result.stdout == body

    @respx.mock
    def test_leading_slash_is_optional(self, run_cli) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/types").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="[]"),
        )

        result = run_cli("api", "get", "samples/types", "--token", TOKEN)

        assert result.exit_code == 0
        assert route.called

    @respx.mock
    def test_params_are_url_encoded(self, run_cli) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )

        run_cli(
            "api", "get", "/samples/search",
            "--param", "name=rna seq", "--param", "count=100",
            "--token", TOKEN,
        )

        params = route.calls[0].request.url.params
        assert params.get("name") == "rna seq"
        assert params.get("count") == "100"

    @respx.mock
    def test_repeated_param_key_is_preserved(self, run_cli) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )

        run_cli(
            "api", "get", "/samples/search",
            "--param", "sample_types=rna", "--param", "sample_types=atac",
            "--token", TOKEN,
        )

        items = route.calls[0].request.url.params.multi_items()
        assert ("sample_types", "rna") in items
        assert ("sample_types", "atac") in items

    @respx.mock
    def test_sends_bearer_token(self, run_cli) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )

        run_cli("api", "get", "/me", "--token", TOKEN)

        assert route.calls[0].request.headers["Authorization"] == f"Bearer {TOKEN}"

    def test_question_mark_in_path_is_usage_error(self, run_cli) -> None:
        result = run_cli(
            "api", "get", "/samples/search?name=x", "--token", TOKEN, "--json",
        )

        assert result.exit_code == 2
        assert result.stdout == ""
        assert "--param" in json.loads(result.stderr)["message"]

    def test_param_without_equals_is_usage_error(self, run_cli) -> None:
        result = run_cli(
            "api", "get", "/pipelines", "--param", "broken", "--token", TOKEN,
            "--json",
        )

        assert result.exit_code == 2
        assert result.stdout == ""
        assert "message" in json.loads(result.stderr)

    @respx.mock
    def test_not_found_maps_to_exit_code_and_json_envelope(self, run_cli) -> None:
        error_message = "No such pipeline"
        respx.get(f"{DEFAULT_BASE_URL}/pipelines/999").mock(
            return_value=httpx.Response(
                HTTPStatus.NOT_FOUND, json={"error": error_message},
            ),
        )

        result = run_cli(
            "api", "get", "/pipelines/999", "--token", TOKEN, "--json",
        )

        assert result.exit_code == 4
        assert result.stdout == ""
        document = json.loads(result.stderr)
        assert document["message"] == error_message
        assert document["status_code"] == int(HTTPStatus.NOT_FOUND)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run pytest tests/unit/cli/test_api.py -v`
Expected: FAIL — `api` is not a recognised resource (argparse error / exit 2) for every test, since the command does not exist yet.

- [ ] **Step 3: Implement the `_api` module**

Create `flowbio/cli/_api.py`:

```python
"""The ``flowbio api`` command group — read-only API passthrough.

A single ``api get <path>`` verb issues an authenticated GET to an
arbitrary path under the configured base URL and writes the response body
to stdout verbatim, so a caller can pipe it straight through ``jq``. The
command is GET-only by construction, so it cannot mutate remote state.
"""
from __future__ import annotations

import argparse

from flowbio.cli._exit_codes import CliUsageError, ExitCode
from flowbio.cli._output import Output
from flowbio.v2.client import Client


def register(
    resource: argparse.ArgumentParser, global_parent: argparse.ArgumentParser,
) -> None:
    """Register the ``api`` verbs on the resource parser."""
    verbs = resource.add_subparsers(dest="verb", metavar="<verb>")
    get = verbs.add_parser(
        "get",
        parents=[global_parent],
        help="Issue a GET to an API path and print the raw response body.",
        description=(
            "Issue an authenticated GET to a path under the Flow API base URL "
            "and write the raw response body to stdout."
        ),
    )
    get.set_defaults(command_parser=get, handler=_get_command)
    get.add_argument(
        "path",
        metavar="PATH",
        help="API path relative to the base URL, e.g. /samples/search.",
    )
    get.add_argument(
        "--param",
        metavar="KEY=VALUE",
        action="append",
        help="Query parameter (repeatable); the value is URL-encoded.",
    )


def _get_command(args: argparse.Namespace, client: Client, output: Output) -> ExitCode:
    """Issue the GET and write the raw response body to stdout.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` on success.
    :raises CliUsageError: If the path carries a query string or a
        ``--param`` value is missing its ``=``.
    """
    if "?" in args.path:
        raise CliUsageError(
            "Query parameters go in --param KEY=VALUE, not the path.",
        )
    params = _parse_params(args.param)
    output.emit_raw(client.get_raw(args.path, params=params))
    return ExitCode.SUCCESS


def _parse_params(raw: list[str] | None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in raw or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise CliUsageError(
                f"--param must be KEY=VALUE, got {item!r}.",
            )
        pairs.append((key, value))
    return pairs
```

- [ ] **Step 4: Register the `api` resource in the parser**

In `flowbio/cli/_parser.py`, add the import next to the existing resource imports (after line 16):

```python
from flowbio.cli._api import register as register_api
```

Then register the resource inside `build_parser`, after the `samples` block (after line 56):

```python
    api_parser = resources.add_parser(
        "api",
        parents=[global_parent],
        help="Read-only API access (arbitrary GET passthrough).",
        description="Issue read-only GET requests to the Flow API.",
    )
    api_parser.set_defaults(command_parser=api_parser)
    register_api(api_parser, global_parent)
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/cli/test_api.py -v`
Expected: PASS (8 tests).

- [ ] **Step 6: Run the full CLI + v2 suites to confirm no regressions**

Run: `uv run pytest tests/unit/cli tests/unit/v2 -q`
Expected: PASS (all existing tests still green).

- [ ] **Step 7: Commit**

```bash
git add flowbio/cli/_api.py flowbio/cli/_parser.py tests/unit/cli/test_api.py
git commit -m "feat(cli): add read-only 'api get' passthrough command

The flow-ai skill reads Flow via curl with the token attached through a
command substitution, which Claude Code cannot auto-approve, so every
read prompts for permission. Add 'flowbio api get <path> [--param k=v]',
a GET-only command that resolves credentials itself and writes the raw
response body to stdout, giving the skill a single allowlistable command.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Document the command in the CLI docs

**Files:**
- Modify: `source/cli.rst`

**Interfaces:**
- Consumes: nothing (documentation only).
- Produces: nothing consumed by later tasks.

Per the repo CLI-docs convention, do **not** duplicate `--help` output. Add a short concept note plus one worked example.

- [ ] **Step 1: Locate the insertion point**

Run: `grep -n "^~\|^-\|^=\|upload\|samples\|data" source/cli.rst | head -40`
Expected: reveals the section structure (per-command headings) so the new `api get` subsection matches the existing heading style.

- [ ] **Step 2: Add an `api get` subsection**

Insert a subsection consistent with the file's existing heading style and prose. Content to convey (adapt heading underline characters to match the file):

```rst
``api get`` — read-only API passthrough
----------------------------------------

Issue an authenticated ``GET`` to any path under the Flow API base URL and
print the raw response body to stdout. Query values go through ``--param``
(repeatable), which URL-encodes them; a ``?`` in the path is rejected. The
command is read-only, so it never changes remote state.

Credentials follow the standard precedence (see above): with a token file at
``~/.config/flow/api-token`` no flags are needed.

.. code-block:: console

   $ flowbio api get /samples/search --param name=rna-seq --param count=100 | jq '.count'
   42

On error the process exits with the standard code (``4`` for not found, ``3``
for auth, ``5`` for a bad request) and, under ``--json``, writes
``{"message": ..., "status_code": ...}`` to stderr.
```

- [ ] **Step 3: Build the docs to confirm no RST errors (if the docs build is wired up)**

Run: `ls docs/Makefile source/conf.py 2>/dev/null && echo "docs present"`
If a Sphinx build is configured (e.g. `uv run make -C docs html` or `uv run sphinx-build`), run it and confirm no warnings for `cli.rst`. If no build is configured, visually confirm the RST heading underline length matches the title length.

- [ ] **Step 4: Commit**

```bash
git add source/cli.rst
git commit -m "docs(cli): document the api get passthrough command

Cover the read-only concept, the --param encoding rule, credential
precedence, and the exit-code contract with one worked example, per the
CLI-docs convention of not duplicating --help output.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

**Spec coverage:**
- Command shape `flowbio api get <path> [--param KEY=VALUE ...]` → Task 3 (parser) ✓
- New `api` resource beside `data`/`samples` → Task 3 (`_parser.py`) ✓
- Path relative to base URL, leading slash optional → Task 3 tests `test_leading_slash_is_optional`; join reuses `HttpTransport._url` (Task 1) ✓
- Query values only via `--param`, URL-encoded → Task 3 `test_params_are_url_encoded`; httpx encodes the pairs ✓
- `?` in path rejected with usage error pointing at `--param` → Task 3 `test_question_mark_in_path_is_usage_error` ✓
- Public `Client` read primitive wrapping `get_bytes`-style transport → Task 1 (`get_text`/`get_raw`; returns text rather than bytes — see note) ✓
- Success: exit 0, raw body verbatim to stdout, `--json` does not reshape → Task 2 (`emit_raw`) + Task 3 `test_writes_raw_body_to_stdout_verbatim` ✓
- Failure: `FlowApiError` → existing `_dispatch` → stderr envelope + status→exit-code mapping → Task 3 `test_not_found_maps_to_exit_code_and_json_envelope` ✓
- Safety: GET-only, host-constrained → no method arg (Task 3); path joined onto base URL (Task 1) ✓
- Credentials via existing `resolve_credentials` (default token file needs no flags) → reused unchanged by `_dispatch`; `test_sends_bearer_token` confirms auth reaches the request ✓
- Docs → Task 4 ✓

**Deviation from spec (intentional):** the spec described raw output as *bytes*; the primitive returns *text* (`response.text`) and `emit_raw` writes to the text stdout the `run_cli` fixture captures. Flow API responses are JSON text and the skill pipes them through `jq`, so text is the correct, testable shape. Binary bulk downloads remain out of scope (the skill keeps its dedicated download path), matching the spec's out-of-scope list.

**Placeholder scan:** No TBD/TODO; every code step shows complete code; the only adapt-to-context step is the RST heading underline in Task 4, which is inherent to editing an existing doc and is bounded by an explicit instruction.

**Type consistency:** `get_text` / `get_raw` share signature `(path: str, params: list[tuple[str, str]] | None = None) -> str` across Tasks 1 and 3; `_parse_params` returns `list[tuple[str, str]]` matching that `params` type; `emit_raw(body: str) -> None` matches its Task 3 call site; `register`/`_get_command` signatures mirror the existing `_data.py` handlers.
