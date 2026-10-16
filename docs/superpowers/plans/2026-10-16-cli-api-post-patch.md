# `flowbio api post|patch` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `flowbio api post PATH --body FILE|-` and `flowbio api patch PATH --body FILE|-`, so the flow-ai skill can call the new agent-writable v2 endpoints (`POST /v2/projects`, `PATCH /v2/projects/{id}`, `PATCH /v2/samples/{id}`) through one allowlistable command, the way it already reads through `api get`.

**Architecture:** One new transport primitive, `HttpTransport.send_text`, sends a JSON body with a given method and returns the raw response text. `Client.post_raw` and `Client.patch_raw` sit on top of it, next to `get_raw`. The `api` resource gets two more verbs that share one handler, parameterised by the client method. The body is read as text (from a file, or stdin for `-`) and sent **verbatim** with `Content-Type: application/json`. The server is the source of truth: malformed JSON comes back as its 4xx (exit 5), the same as any other invalid input. Success and error output reuse what `api get` already does: the raw body on stdout via `Output.emit_raw`, and errors through `_dispatch`'s `FlowApiError` handler, so Problem Details are passed through under `problem` with `--json`.

**Tech Stack:** Python 3.11+, argparse, httpx, respx + pytest (in-process `run_cli` fixture).

**Spec:** `/Users/mhusbyn/conductor/workspaces/flow-api/halifax/docs/superpowers/specs/2026-10-15-ai-agent-write-scope-design.md` (section *flowbio*, PR 5)

## Global Constraints

- Verbs are exactly `post` and `patch`. There is no `api delete`, and no generic `--method` option.
- `--body FILE|-` is required; `-` reads stdin.
- Write verbs never fall back to anonymous: the `allow_anonymous` default (`False`) applies.
- Same transport, token handling, raw-stdout output and stderr error contract as `api get`. Do not change `_transport._unpack_error_body` or `_dispatch`.
- Version: `setup.py` is already `0.14.0` and 0.14.0 is **not on PyPI yet** (PyPI latest is 0.13.0). This PR ships inside 0.14.0 with no version bump. If 0.14.0 is published before this merges, bump to 0.15.0 in its own `chore` commit, and the skill's pin moves with it.
- Repo rules: test-first; test through `run_cli` / public `Client` / `HttpTransport`, never `_`-prefixed functions; comments only for a non-obvious *why*; no spec/plan IDs in code.
- Commit footer: `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.

## Review Focus

1. **The server refuses a field (e.g. `project` on a sample, 422 `validation_error`)**: exit 5, stdout empty, and `--json` stderr carries the server's `problem` unchanged, because the skill relays that refusal to the user. → Task 2, `test_validation_problem_is_passed_through`.
2. **No token available**: a write must not go out anonymously. Without a token and with non-interactive stdin, exit 2 and no request sent. → Task 2, `test_requires_credentials`.
3. **`--body` names a missing file**: exit 2 with a clean message and no request, not a traceback. → Task 2, `test_missing_body_file_is_usage_error`.
4. **Body is sent byte-for-byte**: no re-serialisation (key order and unicode kept), and `Content-Type: application/json` is set. → Task 1, `test_sends_body_verbatim_as_json`.
5. **`POST` answers 201 Created**: treated as success (exit 0, body on stdout), not as an unexpected status. → Task 2, `test_post_writes_created_body_to_stdout`.

---

### Task 1: Raw write primitive on transport and client

**Files:**
- Modify: `flowbio/v2/_transport.py` (add `send_text` after `post`)
- Modify: `flowbio/v2/client.py` (add `post_raw`, `patch_raw` after `get_raw`)
- Test: `tests/unit/v2/test_transport.py`, `tests/unit/v2/test_client.py`

**Interfaces:**
- Consumes: `HttpTransport._request`, `_raise_for_error`, `_url` (existing).
- Produces:
  - `HttpTransport.send_text(self, method: HTTPMethod, path: str, body: str) -> str`: sends `content=body` with header `Content-Type: application/json`, raises `FlowApiError` on non-2xx, returns `response.text`.
  - `Client.post_raw(self, path: str, body: str) -> str` and `Client.patch_raw(self, path: str, body: str) -> str`: delegate to `send_text` with `HTTPMethod.POST` / `HTTPMethod.PATCH`. Docstrings follow `get_raw`'s: a low-level write escape hatch for the CLI's `api post` / `api patch`; the body is a JSON document sent unchanged.

- [ ] **Step 1: Write the failing transport tests** in a new `class TestTransportSendText`:
  - `test_sends_body_verbatim_as_json`: `body = '{"name": "Ünïcode", "a": 1}'` sent with `HTTPMethod.PATCH` to `/v2/samples/1`; assert `route.calls[0].request.content == body.encode()` and `request.headers["Content-Type"] == "application/json"`.
  - `test_returns_raw_response_body`: the response `text=` is returned unchanged.
  - `test_raises_flow_api_error_on_non_success`: 404 → `pytest.raises(NotFoundError)`.
- [ ] **Step 2: Run** `pytest tests/unit/v2/test_transport.py -k SendText -v` and expect FAIL (`AttributeError: send_text`).
- [ ] **Step 3: Implement `HttpTransport.send_text`.**
- [ ] **Step 4: Run** the same command and expect PASS.
- [ ] **Step 5: Write the failing client tests** in `class TestClientWriteRaw`: `test_post_raw_posts_body_and_returns_raw_response` and `test_patch_raw_patches_body_and_returns_raw_response`. Each mocks `respx.post` / `respx.patch` respectively, so the wrong verb fails, and asserts both the request content and the returned text.
- [ ] **Step 6: Run** `pytest tests/unit/v2/test_client.py -k WriteRaw -v` and expect FAIL.
- [ ] **Step 7: Implement `Client.post_raw` and `Client.patch_raw`.**
- [ ] **Step 8: Run** `pytest tests/unit/v2 -q` and expect all to pass.
- [ ] **Step 9: Commit** `feat(v2): add Client.post_raw and Client.patch_raw raw write primitives`.

### Task 2: `api post` and `api patch` verbs, plus docs

**Files:**
- Modify: `flowbio/cli/_api.py` (register both verbs, add the shared handler and body reading, update the module docstring: no longer "read-only / GET-only"; it is GET, POST and PATCH, with DELETE deliberately absent)
- Modify: `flowbio/cli/_parser.py:60-63` (the `api` help/description stop saying read-only, e.g. "Raw API access: GET, POST and PATCH passthrough.")
- Modify: `source/cli.rst` (rename section `api get` → `api`; add `api post` / `api patch` with the synopsis, the rules that the body is sent verbatim, a token is required, and the server validates, and one worked example: `flowbio api post /v2/projects --body - <<< '{"name": "RNA-seq 2026"}'`)
- Test: `tests/unit/cli/test_api.py`

**Interfaces:**
- Consumes: `Client.post_raw`, `Client.patch_raw` (Task 1); `existing_file` (`flowbio/cli/_files.py`); `Output.emit_raw`.
- Produces: CLI verbs `api post PATH --body FILE|-` and `api patch PATH --body FILE|-`, no `allow_anonymous`, `--body` required (`metavar="FILE|-"`, help pointing to `/v2/reference` for body schemas).

Implementation shape: a `_register_write_verb(verbs, name, global_parent, send)` helper, called twice, where `send` is `Client.post_raw` / `Client.patch_raw` (stored via `set_defaults(send=...)`). One `_write_command` handler reads the body (`sys.stdin.read()` for `-`, otherwise `existing_file(Path(arg)).read_text()`), calls `args.send(client, args.path, body)` and emits the result with `emit_raw`.

- [ ] **Step 1: Write the failing CLI tests** in `class TestApiWrite`. Parametrise over `("post", respx.post)` and `("patch", respx.patch)` where the case applies:
  - `test_sends_body_file_and_writes_raw_response` (parametrised): `tmp_path / "body.json"` holding `'{"name": "x"}'`; assert exit 0, `stdout == response_body`, request content equals the file bytes, and the bearer token is sent.
  - `test_reads_body_from_stdin` (parametrised): `monkeypatch.setattr("sys.stdin", io.StringIO(body))`, `--body -`; request content equals `body`.
  - `test_post_writes_created_body_to_stdout`: the server answers `HTTPStatus.CREATED`; exit 0, stdout is the body.
  - `test_missing_body_file_is_usage_error`: exit 2, `stdout == ""`, the `--json` stderr `message` contains the path, and `not route.called`.
  - `test_body_is_required`: `api patch /v2/samples/1` with no `--body` gives exit 2.
  - `test_requires_credentials` (uses the `no_credentials` fixture, and patches `sys.stdin` to a non-tty `StringIO`): exit 2 and `not route.called`. The near miss is `api get`'s existing anonymous test.
  - `test_validation_problem_is_passed_through`: `problem_response(HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", "`project` can't be changed with this endpoint: …")`; exit 5, `stdout == ""`, and `json.loads(stderr) == {"message": problem["detail"], "status_code": 422, "problem": problem}`.
  - `test_there_is_no_delete_verb`: `api delete /v2/projects/1 --token …` gives exit 2.
- [ ] **Step 2: Run** `pytest tests/unit/cli/test_api.py -k ApiWrite -v` and expect FAIL (argparse rejects the `post`/`patch` choice, exit 2 where 0 is asserted).
- [ ] **Step 3: Implement the verbs in `_api.py`** as shaped above.
- [ ] **Step 4: Run** `pytest tests/unit/cli/test_api.py -v` and expect PASS, including every existing `TestApiGet` test.
- [ ] **Step 5: Update the `_api.py` docstring, the `_parser.py` help and `source/cli.rst`.** Check the docs with `make html` (Sphinx). It must produce no new warnings.
- [ ] **Step 6: Run** `pytest -q` (Python 3.13 venv) and expect the full suite to pass.
- [ ] **Step 7: Commit** `feat(cli): add api post and api patch passthrough verbs`. The body says why: the agent-writable v2 endpoints, and that there is no delete verb on purpose.

### Then

`/adversarial-review` until it converges, then `/ship-pr-review` to open the PR against `master` (CI: unit tests on 3.11/3.12/3.13 plus claude-review; this repo has no SonarQube). Publishing 0.14.0 to PyPI stays Martin's step, after merge.
