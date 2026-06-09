# Implementation Plan: flowbio Command-Line Interface

**Branch**: `001-flowbio-cli` | **Date**: 2026-06-05 (updated 2026-06-09) | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-flowbio-cli/spec.md`

> **2026-06-09 update**: Reflects (a) the new `samples annotation-template`
> command added to User Story 5 (FR-043/FR-044), and (b) the implementation's
> actual module layout — the domain handlers are `_`-prefixed (`_data.py`,
> `_samples.py`) and the parser tree, file validation, and named types live in
> their own `_`-prefixed modules.

## Summary

Add a `flowbio` console command that exposes the existing `flowbio.v2` upload
operations from the terminal, for both humans (concise lines) and automated
agents (`--json`, stable exit codes). The CLI is a thin presentation layer over
the `Client` resources — it adds no protocol logic. Command surface is
resource-namespaced (`flowbio data …`, `flowbio samples …`) mirroring
`client.data` / `client.samples`.

Technical approach: a new `flowbio.cli` package built on **argparse** (standard
library — zero new runtime dependencies, keeping `uvx` cold starts fast per
FR-039/FR-040). Domain command modules (`_data`, `_samples`) receive a constructed
`Client` via dependency injection; cross-cutting concerns (the argparse tree,
credential resolution, output/JSON rendering, exit-code mapping, progress,
local-file validation, CSV sheet parsing) live in shared `_`-prefixed modules.
The CLI is registered as a `console_scripts` entry point.

The `samples annotation-template` command (FR-043/FR-044) wraps the **existing**
`Client.samples.get_annotation_template(sample_type)` library method, which
returns the server-generated Excel workbook bytes — so it needs **no** library
change; the handler writes those bytes to `-o/--output` and refuses to stream
binary to a terminal. The one small **additive** library change the feature still
needs is for `batch-template`: expose on `MetadataAttribute` whether the attribute
permits a free-text annotation, so the CLI can emit annotation companion columns.

## Technical Context

**Language/Version**: Python 3.11+ (matches the `flowbio` package floor `python_requires=">=3.11"` in `setup.py`); modules use `from __future__ import annotations`.

**Primary Dependencies**: `argparse` (stdlib, CLI parsing), `csv` (stdlib, sample sheet I/O), `getpass` (stdlib, password prompt), `json` (stdlib, `--json` output); existing `tqdm` for progress. **No new third-party runtime dependency.**

**Storage**: N/A — reads local files to upload and writes template/output files; no persistent state.

**Testing**: `pytest` with `respx` (existing stack). CLI handlers invoked in-process with an argv list; assertions on captured stdout/stderr and the returned exit code, with the HTTP layer mocked via `respx` (or a fake transport).

**Target Platform**: Cross-platform CLI (Linux, macOS, Windows) on CPython 3.11+.

**Project Type**: Single project — CLI added inside the existing `flowbio` library package.

**Performance Goals**: Fast on-demand cold start under `uvx --from "flowbio==X.Y.Z" flowbio …`; achieved by keeping the install closure lean (no new deps). No throughput target — upload speed is bounded by the existing chunked uploader.

**Constraints**: `--json` mode emits exactly one JSON document on stdout and nothing else there; progress and human messaging go to stderr; password never accepted via flag or environment variable; tokens never logged or echoed.

**Scale/Scope**: 2 resource groups, 6 commands (`data upload`, `samples upload`, `samples batch-template`, `samples upload-batch`, `samples annotation-template`, `samples upload-multiplexed`), 6 documented exit codes.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Assessment |
|-----------|------------|
| **I. Test-First (NON-NEGOTIABLE)** | PASS — every command and shared module is driven test-first (failing CLI test → implement → green). `tasks.md` will order tests before implementation per command. |
| **II. Domain-Organized, Loosely-Coupled** | PASS — CLI organized by domain (`cli/_data.py`, `cli/_samples.py`); cross-cutting infra (`_parser`, `_auth`, `_output`, `_exit_codes`, `_progress`, `_files`, `_sheet`, `_types`, `_main`) shared. Handlers receive a `Client` via dependency injection; they never reach `httpx` or globals. |
| **III. Encapsulation & Strong Typing** | PASS — all CLI internals are `_`-prefixed; the public surface is the command line itself (documented in `contracts/`). Full type hints on handler signatures; reuses frozen `v2` models. |
| **IV. Documented, Agent- & Human-Friendly** | PASS — dual human/`--json` output, stable exit codes, actionable errors routed through the typed `FlowApiError` hierarchy; docstrings on public functions; user docs ship with the commands (FR-041/FR-042). |
| **V. Simplicity & Readability** | PASS — argparse over a third-party CLI framework (YAGNI; lean closure); no speculative options beyond the spec. |
| **VI. Secret & Credential Safety** | PASS — password only via interactive `getpass` prompt (FR-008); tokens never logged or placed in `repr`/errors; non-interactive sessions fail fast rather than echoing prompts. |
| **VII. Backwards-Compatible Evolution** | PASS — purely additive: new `flowbio.cli` package, new `console_scripts` entry point, and one additive `MetadataAttribute` field (for `batch-template`). `annotation-template` adds no library change — it wraps the existing `get_annotation_template`. No existing public signature changes. Warrants a MINOR version bump. |

**Result**: All gates pass. No deviations to record — Complexity Tracking is empty.

## Project Structure

### Documentation (this feature)

```text
specs/001-flowbio-cli/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output — one contract per command
│   ├── cli-conventions.md
│   ├── data-upload.md
│   ├── samples-upload.md
│   ├── samples-batch-template.md
│   ├── samples-upload-batch.md
│   ├── samples-annotation-template.md
│   └── samples-upload-multiplexed.md
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
flowbio/
├── cli/
│   ├── __init__.py
│   ├── __main__.py          # `python -m flowbio.cli` entry
│   ├── _main.py             # global-option resolution, dispatch, top-level exit-code handling
│   ├── _parser.py           # argparse tree; global options accepted identically pre/post verb
│   ├── _auth.py             # credential resolution precedence + non-interactive guard
│   ├── _output.py           # human vs --json rendering; clean-stdout discipline
│   ├── _exit_codes.py       # ExitCode enum + FlowApiError → exit-code mapping
│   ├── _progress.py         # stderr progress, --no-progress wiring into ClientConfig
│   ├── _files.py            # local-file existence/readability validation (CliUsageError)
│   ├── _types.py            # internal named types tightening str/object values
│   ├── _sheet.py            # CSV sample-sheet parsing + pre-flight validation (upload-batch)
│   ├── _data.py             # `data upload` handler
│   └── _samples.py          # samples upload / batch-template / upload-batch / annotation-template / upload-multiplexed
└── v2/
    └── samples.py           # existing: get_annotation_template (annotation-template wraps it);
                             # additive (for batch-template): MetadataAttribute "allows annotation" flag

tests/unit/cli/
├── __init__.py
├── conftest.py              # argv runner + captured stdout/stderr/exit-code helper
├── test_main.py            # parsing, global option placement, help/usage exit codes, --version
├── test_auth.py            # credential precedence, prompts, non-interactive failure
├── test_output.py         # human/json rendering, error documents, exit-code mapping
├── test_progress.py       # stderr progress + --no-progress
├── test_files.py          # local-file validation
├── test_sheet.py          # CSV parse + per-row validation + relative path resolution (upload-batch)
├── test_data.py           # data upload
└── test_samples.py        # samples upload / batch-template / upload-batch / annotation-template / upload-multiplexed

docs/                        # user-facing CLI documentation (FR-041/FR-042)
└── cli.md (integrated into the existing Sphinx tree)

setup.py                     # add console_scripts: flowbio = flowbio.cli._main:main
```

**Structure Decision**: Single-project layout. The CLI lives at `flowbio/cli/`
inside the existing package so it ships in the same distribution and the
`console_scripts` entry point resolves under `uvx --from "flowbio==X.Y.Z"`.
Domain handlers (`_data.py`, `_samples.py`) sit beside `_`-prefixed shared
infrastructure, matching Principle II. Every CLI module is `_`-prefixed: the
public surface is the command line itself, so the handlers are private to the
package (Principle III) — hence `_data.py`/`_samples.py` rather than
`data.py`/`samples.py`. The only change outside the new package is an additive
field on `flowbio/v2/samples.py::MetadataAttribute` (for `batch-template`);
`annotation-template` reuses the existing `get_annotation_template` method.

The chosen layout is "package-by-layer, named-by-domain": the CLI is a separate
presentation layer whose modules are still organized by domain
(`cli/_samples.py` mirrors `v2/samples.py`).

#### Considered alternative: co-locate CLI handlers inside the domain (rejected)

An alternative is to fold each domain's command handler into its library
module/package — either directly into `v2/samples.py`, or by promoting each
domain to a package and adding a delivery module (e.g. `v2/samples/cli.py`,
`v2/samples/queries.py`). This maximizes per-domain cohesion and, in the package
form, the namespace leak is avoidable (a curated `__init__.py` need not export
`cli`).

It was rejected because, in ports-and-adapters terms, **a CLI is a driving
adapter that belongs in the outermost ring and must depend inward on the domain —
never the reverse.** Placing `cli.py` *inside* the domain package inverts that
arrow at the dependency-graph and shipped-artifact level even when the symbol is
unexported: `flowbio.v2` is a published, independently versioned client SDK, and
programmatic consumers would then carry `argparse`/output/exit-code machinery in
their import path (against the lean-closure goal of FR-040, Principles III & V).
A single CLI process also composes multiple domains plus cross-cutting concerns
(global options, the argparse tree, dispatch, auth precedence, exit codes), so a
central presentation layer is required regardless; per-domain `cli.py` files only
smear that layer across domain packages while paying the dependency-direction
cost. Note also that `flowbio` is a client SDK rather than a DDD domain-model
application — the real domain lives server-side — so the rule that actually
applies here is the dependency direction, which the chosen layout honors.

A reasonable **future** direction (out of scope for this feature, which needs
only the additive `MetadataAttribute` field) is to promote `v2/<domain>` to
packages (`v2/samples/{models,queries,mutations,validation}.py`) for room to
grow, while keeping the CLI delivery layer separate under `cli/`. That is a
standalone refactor to be proposed and scheduled on its own per the
constitution's refactoring workflow.

## Complexity Tracking

> No constitutional violations — this section is intentionally empty.
