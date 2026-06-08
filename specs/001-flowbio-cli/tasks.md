---
description: "Task list for flowbio CLI implementation"
---

# Tasks: flowbio Command-Line Interface

**Input**: Design documents from `/specs/001-flowbio-cli/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: MANDATORY per Constitution Principle I (Test-First, NON-NEGOTIABLE). Every behavior has a failing test written and confirmed red before its implementation task. Test tasks precede their implementation tasks for the same behavior.

**Organization**: Tasks are grouped by user story. Each story is an independently testable increment delivered on top of the shared foundation.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1–US5)
- Exact file paths are included in every task

## Path Conventions

Single-project layout (per plan.md): CLI under `flowbio/cli/`, tests under `tests/unit/cli/`, the one additive library change in `flowbio/v2/samples.py`, user docs in `docs/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the CLI package skeleton, register the entry point, and stand up the test harness.

- [X] T001 Create the `flowbio/cli/` package skeleton: `flowbio/cli/__init__.py` and `flowbio/cli/__main__.py` (the latter dispatching to `flowbio.cli._main:main` so `python -m flowbio.cli` works)
- [X] T002 In `setup.py`, add `"flowbio.cli"` to `packages` and register the console script `entry_points={"console_scripts": ["flowbio = flowbio.cli._main:main"]}`
- [X] T003 [P] Create `tests/unit/cli/__init__.py` and `tests/unit/cli/conftest.py` with an argv-runner fixture that invokes the CLI in-process, captures stdout/stderr and the returned exit code, and mocks the HTTP layer via `respx` (mirroring `tests/unit/v2/conftest.py`)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The shared `_`-prefixed infrastructure every command needs to run at all — exit-code contract, output rendering, credential resolution, progress wiring, and the top-level parser/dispatch.

**⚠️ CRITICAL**: No user-story command can run until this phase is complete.

### Tests for Foundational (MANDATORY — write first) ⚠️

> Write these tests FIRST, run them, and confirm they FAIL (red) before any implementation task below.

- [X] T004 [P] Write failing tests for the exit-code contract and output rendering in `tests/unit/cli/test_output.py`: `ExitCode` values (0/1/2/3/5 and NOT_FOUND=4 per data-model), `exit_code_for(exc)` mapping (`AuthenticationError→3`, `NotFoundError→4`, `BadRequestError`/`AnnotationValidationError→5`, other `FlowApiError→1`, CLI usage→2), human single result line on stdout, `--json` exactly one document on stdout and nothing else, and the error JSON document on stderr carrying `message` + status code (FR-035, FR-037, FR-038)
- [X] T005 [P] Write failing tests for credential resolution in `tests/unit/cli/test_auth.py`: precedence `--login` > `--token`/`FLOW_API_TOKEN` > `--token-file`/`FLOW_TOKEN_FILE` > default `~/.config/flow/api-token` > prompt; base-URL flag > env > default; named token file missing/empty → exit 2; `--token` with `--login` → exit 2; prompt needed but non-interactive stdin → exit 2 fail-fast; password never sourced from flag/env (FR-006…FR-013)
- [X] T006 [P] Write failing tests for the top-level parser and dispatch in `tests/unit/cli/test_main.py`: global options accepted identically before and after the verb (FR-004), `flowbio --version` prints version exit 0 (FR-005), explicit help is available and exits 0 at every level (`flowbio --help`, `flowbio data --help`, and a representative `flowbio samples upload --help` each emit help text and exit 0), bare `flowbio` and `flowbio data` (no verb) show help exit 2, unknown resource/verb exit 2 (FR-003)

### Implementation for Foundational

- [X] T007 [P] Implement `flowbio/cli/_exit_codes.py`: `ExitCode(IntEnum)` (SUCCESS=0, RUNTIME=1, USAGE=2, AUTH=3, NOT_FOUND=4, BAD_REQUEST=5) and `exit_code_for(exc)` mapping from the `FlowApiError` hierarchy (data-model.md §ExitCode)
- [X] T008 [US1] Implement `flowbio/cli/_output.py`: human vs `--json` rendering, single-document stdout discipline, advisories/errors to stderr, and the error JSON document (message + status code) — uses `ExitCode` from T007
- [X] T009 Implement `flowbio/cli/_auth.py`: `resolve_credentials(...)` returning `flowbio.v2.auth.Credentials` + resolved base URL with the FR-009 precedence, the named-file and conflicting-flag usage errors, the non-interactive guard, and a `getpass`-only password prompt (depends on T007)
- [X] T010 [P] Implement `flowbio/cli/_progress.py`: route progress to stderr and translate `--no-progress` into `ClientConfig(show_progress=False)` (FR-036)
- [X] T011 Implement `flowbio/cli/_main.py`: argparse tree (`flowbio <resource> <verb>`), global options registered both before and after the verb, `--version`, help/usage exit-code behaviour, and dispatch that constructs the `Client` (via T009 credentials + base URL, T010 progress config) and injects it into domain handlers (depends on T007, T008, T009, T010)

**Checkpoint**: The CLI parses, authenticates, renders output, and maps exit codes — handlers can now be added.

---

## Phase 3: User Story 1 - Upload a generic data file (Priority: P1) 🎯 MVP

**Goal**: `flowbio data upload PATH` uploads a file and reports its data identifier, exercising the full pipeline (parse → auth → call library → render → exit code).

**Independent Test**: Run `flowbio data upload ./counts.tsv` against a test backend → identifier printed, exit 0; re-run with `--json` → a single `{"id": "..."}` document on stdout.

### Tests for User Story 1 (MANDATORY — write first) ⚠️

- [X] T012 [P] [US1] Write failing tests in `tests/unit/cli/test_data.py` covering US1 scenarios 1–6: upload + identifier line (exit 0); `--json` single `{"id": ...}` doc on stdout only; `--filename` overrides stored name; `--directory` uploads as directory archive; server rejection (bad data type) → exit 5; invalid token → exit 3 (contracts/data-upload.md)

### Implementation for User Story 1

- [X] T013 [US1] Implement `flowbio/cli/data.py` `data upload` handler wrapping `client.data.upload_data(path, filename=..., data_type=..., is_directory=...)` (`--data-type` optional, sent as-is, not pre-validated) and register the `data upload` subcommand in `flowbio/cli/_main.py` with `help=`/description text on every argument so per-command `--help` is self-documenting (FR-003, SC-008) (FR-014, FR-015)
- [X] T014 [US1] Document `data upload` (options, output modes, exit codes, worked example) in `docs/cli.md` (FR-041, FR-042)

**Checkpoint**: MVP — a generic file uploads end-to-end and is independently demonstrable.

---

## Phase 4: User Story 2 - Upload a single sequencing sample (Priority: P2)

**Goal**: `flowbio samples upload` creates a single demultiplexed sample (single- or paired-end) with metadata supplied as `key=value` pairs and/or a JSON object.

**Independent Test**: Run `flowbio samples upload --name s1 --sample-type rna_seq --reads1 r1.fq.gz` → identifier printed; repeat with `--reads2`, `--metadata`, and `--metadata-json`.

### Tests for User Story 2 (MANDATORY — write first) ⚠️

- [ ] T015 [P] [US2] Write failing tests in `tests/unit/cli/test_samples.py` covering US2 scenarios 1–6: single-ended create (exit 0); `--reads2` → paired-end; repeated `--metadata key=value` (split on first `=`, incl. value containing `=`); `--metadata-json` object; same key in both sources → exit 2 before upload; `<identifier>__annotation` companion passed through (contracts/samples-upload.md)

### Implementation for User Story 2

- [ ] T016 [US2] Implement metadata parsing/merging in `flowbio/cli/samples.py` (`MetadataInput`: split on first `=`, merge `--metadata` with `--metadata-json`, conflicting key → USAGE error, annotation companion passthrough) (FR-018, FR-019)
- [ ] T017 [US2] Implement the `samples upload` handler in `flowbio/cli/samples.py` wrapping `client.samples.upload_sample(name, sample_type, data, project_id=..., organism_id=..., metadata=...)` (sample type sent as-is) and register the subcommand in `flowbio/cli/_main.py` with `help=`/description text on every argument so per-command `--help` is self-documenting (FR-003, SC-008) (FR-016, FR-017)
- [ ] T018 [US2] Document `samples upload` (metadata rules, output, exit codes, worked example) in `docs/cli.md` (FR-041, FR-042)

**Checkpoint**: Single-sample upload works independently; the per-row building block for batch upload exists.

---

## Phase 5: User Story 3 - Generate a sample-sheet template (Priority: P3)

**Goal**: `flowbio samples batch-template --sample-type T` emits a correctly-ordered CSV header (or a `--json` per-column descriptor) plus a required-columns summary.

**Independent Test**: Run `flowbio samples batch-template --sample-type rna_seq` → CSV header (reserved + metadata columns, no `sample_type` column) on stdout, required/optional summary on stderr; `--json` → per-column descriptor list, no CSV.

### Tests for User Story 3 (MANDATORY — write first) ⚠️

- [ ] T019 [P] [US3] Write a failing test in `tests/unit/v2/test_samples.py` for the additive `MetadataAttribute.allows_annotation` field: defaults to `False` when the payload omits the key, and is populated from the `/samples/metadata` response (data-model.md §MetadataAttribute, FR-019/FR-024)
- [ ] T020 [US3] Implement the additive `allows_annotation: bool = False` field on `MetadataAttribute` and populate it in `_create_metadata_attribute` in `flowbio/v2/samples.py` (additive, backwards-compatible — the feature's only library change)
- [ ] T021 [P] [US3] Write failing tests in `tests/unit/cli/test_samples.py` covering US3 scenarios 1–6: CSV header of reserved columns (`name,reads1,reads2,project,organism`) then one column per metadata attribute, with `<id>__annotation` after each annotation-enabled attribute, and no `sample_type` column; required/optional summary on stderr without `--json`; `-o/--output PATH` writes to file; `--json` per-column descriptor list (name, kind, required, options, description) with no CSV; missing `--sample-type` → exit 2 (contracts/samples-batch-template.md)

### Implementation for User Story 3

- [ ] T022 [US3] Implement the `batch-template` handler and `BatchTemplate` descriptor in `flowbio/cli/samples.py` (column ordering, `required` derived from `required` OR chosen type in `required_for_sample_types`, `--json` descriptors, `-o/--output` writing, summary to stderr) sourced from `client.samples.get_metadata_attributes()`, and register the subcommand in `flowbio/cli/_main.py` with `help=`/description text on every argument so per-command `--help` is self-documenting (FR-003, SC-008) (FR-024, FR-025, FR-026)
- [ ] T023 [US3] Document `batch-template` and the sample-sheet schema (reserved columns, metadata-identifier columns, annotation companions) in `docs/cli.md` (FR-041, FR-042)

**Checkpoint**: Template generation works independently and defines the contract consumed by batch upload.

---

## Phase 6: User Story 4 - Upload a batch of samples from a sample sheet (Priority: P4)

**Goal**: `flowbio samples upload-batch --sheet x.csv --sample-type T` validates every row up front, then uploads valid rows sequentially in sheet order, reporting every row's outcome.

**Independent Test**: Author a two-row CSV and run `flowbio samples upload-batch --sheet sheet.csv --sample-type rna_seq` → both rows validated then uploaded with a final counts summary.

### Tests for User Story 4 (MANDATORY — write first) ⚠️

- [ ] T024 [P] [US4] Write failing tests in `tests/unit/cli/test_sheet.py` for `_sheet` parsing and pre-flight validation: reserved vs metadata columns; reads paths resolved relative to the sheet directory (absolute used as-is); empty cells omitted; all per-row errors collected (missing required value, missing reads file on disk, space in name, value outside an attribute's options, required-for-type metadata missing, annotation set without its value / on a non-annotation attribute); non-CSV (`.xlsx`/`.tsv`) rejected with an "export to CSV" message (FR-020…FR-023, FR-028)
- [ ] T026 [P] [US4] Write failing tests in `tests/unit/cli/test_samples.py` covering US4 scenarios 1–7: uniform sample type applied to all rows (exit 0); relative-path resolution; any invalid row (default) reports all errors with 1-based row number + name and uploads nothing → exit 2; `--skip-invalid` skips & reports invalid rows and uploads the rest; sequential upload in row order, default continues past upload failures → exit 1, `--stop-on-error` aborts on the first failing row reporting already-uploaded rows; `--json` document with `uploaded`/`failed`/`skipped` + `counts`; non-CSV sheet → exit 2 (contracts/samples-upload-batch.md)

### Implementation for User Story 4

- [ ] T025 [US4] Implement `flowbio/cli/_sheet.py`: `SampleSheet`/`SheetRow` CSV parsing, relative-path resolution, empty-cell omission, the FR-028 per-row pre-flight validation collecting all errors, and the non-CSV → USAGE rejection (depends on T024)
- [ ] T027 [US4] Implement the `upload-batch` handler and `BatchResult` in `flowbio/cli/samples.py` (parse + validate all rows before any upload; `--skip-invalid`; sequential upload reusing the T017 single-sample path; default-continue vs `--stop-on-error`; exit code: all uploaded→0, pre-flight invalid without `--skip-invalid`→2, any upload failure→1) and register the subcommand in `flowbio/cli/_main.py` with `help=`/description text on every argument so per-command `--help` is self-documenting (FR-003, SC-008) (FR-027…FR-032)
- [ ] T028 [US4] Document `upload-batch` (validation behaviour, `--skip-invalid`/`--stop-on-error`, `--json` shape, worked example) in `docs/cli.md` (FR-041, FR-042)

**Checkpoint**: Batch upload works independently; every row's outcome is reported.

---

## Phase 7: User Story 5 - Upload multiplexed reads with an annotation sheet (Priority: P5)

**Goal**: `flowbio samples upload-multiplexed --reads1 r1.fq.gz --annotation sheet.csv` submits multiplexed reads + annotation sheet and reports data identifiers, the annotation identifier, and any warnings.

**Independent Test**: Run `flowbio samples upload-multiplexed --reads1 r1.fq.gz --annotation annotation.csv` → data identifiers, annotation identifier, and any warnings reported.

### Tests for User Story 5 (MANDATORY — write first) ⚠️

- [ ] T029 [P] [US5] Write failing tests in `tests/unit/cli/test_samples.py` covering US5 scenarios 1–4: submit + report `data_ids`/`annotation_id`/`warnings` (exit 0); `--reads2` → paired-end; warnings reported but upload proceeds by default (`ignore_warnings=True`), `--reject-warnings` rejects; annotation fails server validation → exit 5 (contracts/samples-upload-multiplexed.md)

### Implementation for User Story 5

- [ ] T030 [US5] Implement the `upload-multiplexed` handler in `flowbio/cli/samples.py` wrapping `client.samples.upload_multiplexed_data(reads, annotation, ignore_warnings=...)` (default `ignore_warnings=True`; `--reject-warnings` flips it) reporting ids/annotation/warnings, and register the subcommand in `flowbio/cli/_main.py` with `help=`/description text on every argument so per-command `--help` is self-documenting (FR-003, SC-008) (FR-033, FR-034)
- [ ] T031 [US5] Document `upload-multiplexed` (warning behaviour, output, exit codes, worked example) in `docs/cli.md` (FR-041, FR-042)

**Checkpoint**: All five commands are usable end-to-end and independently demonstrable.

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Consolidated documentation, lean-closure verification, and end-to-end validation across all stories.

- [ ] T032 [P] Add the consolidated docs overview to `docs/cli.md`: authentication resolution order, exit-code contract, human-vs-`--json` output modes, and `uvx --from "flowbio==X.Y.Z"` distribution (FR-039, FR-041, SC-006, SC-008)
- [ ] T033 [P] Verify the install closure adds no new third-party runtime dependency (`setup.py` `install_requires` unchanged) so on-demand `uvx` cold starts stay fast (FR-040)
- [ ] T034 [P] Add edge-case regression tests in `tests/unit/cli/`: metadata value containing `=`, empty sample-sheet cells omitted, and `flowbio --json samples upload …` ≡ `flowbio samples upload … --json` parity (spec Edge Cases)
- [ ] T035 Run the `quickstart.md` scenarios end-to-end against a test backend and confirm each documented exit code, including the non-interactive guard (`< /dev/null` → exit 2, no hang)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately.
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all user stories.
- **User Stories (Phases 3–7)**: All depend on Foundational. US1 (P1) is the MVP; later stories build on shared code but remain independently testable.
- **Polish (Phase 8)**: Depends on the desired user stories being complete.

### User Story Dependencies

- **US1 (P1)**: Foundational only — first runnable command (validates the foundation).
- **US2 (P2)**: Foundational only. Adds the metadata-parsing + single-sample path.
- **US3 (P3)**: Foundational + the additive `MetadataAttribute.allows_annotation` field (T019/T020). Independent of US1/US2.
- **US4 (P4)**: Reuses the US2 single-sample upload path (T017) and the US3 sheet contract; needs `_sheet.py`. Strongest cross-story coupling.
- **US5 (P5)**: Foundational only. Independent of the other sample commands.

### Within Each User Story

- Tests are written and confirmed FAILING (red) before implementation.
- Shared/value objects (`MetadataInput`, `_sheet`, `BatchTemplate`/`BatchResult`) before the handler that uses them.
- Handler registration in `_main.py` after the handler exists.
- Documentation lands with the command (FR-042) — a command is not complete until its docs section exists.

### Parallel Opportunities

- All Setup `[P]` tasks (T003) can run alongside T001/T002 work.
- Foundational tests T004/T005/T006 are fully parallel; among implementation, T007 and T010 are parallel, while T008/T009/T011 follow their dependencies.
- Each story's test task is `[P]` and can be written as soon as its phase starts.
- With multiple developers, once Foundational completes, US1/US2/US3/US5 can proceed in parallel; US4 should follow US2 + US3.

---

## Parallel Example: Foundational Phase

```bash
# Write all foundational tests together (must fail before implementation):
Task T004: "exit-code + output tests in tests/unit/cli/test_output.py"
Task T005: "credential-resolution tests in tests/unit/cli/test_auth.py"
Task T006: "parser/dispatch tests in tests/unit/cli/test_main.py"

# Then the independent implementations:
Task T007: "Implement flowbio/cli/_exit_codes.py"
Task T010: "Implement flowbio/cli/_progress.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 only)

1. Complete Phase 1 (Setup) and Phase 2 (Foundational).
2. Complete Phase 3 (US1 — `data upload`).
3. **STOP and VALIDATE**: upload a file end-to-end, confirm `--json` and exit codes.
4. Ship the MVP if ready.

### Incremental Delivery

Foundation → US1 (MVP) → US2 → US3 → US4 → US5 → Polish. Each story is independently testable and adds value without breaking earlier ones.

---

## Notes

- `[P]` = different files, no dependency on an incomplete task.
- `[Story]` labels map tasks to user stories for traceability; Setup/Foundational/Polish carry no story label.
- Verify every test fails (red) before implementing.
- T008 carries a `[US1]` label only because `_output.py` is first exercised by US1; it is implemented in the Foundational phase as shared infrastructure.
- Commit after each task or logical group; stop at any checkpoint to validate a story independently.
