# Phase 0 Research: flowbio CLI

All Technical Context unknowns are resolved below. Each entry records the
decision, why it was chosen, and the alternatives rejected.

## 1. CLI parsing framework

- **Decision**: Use the standard-library `argparse` with subparsers
  (`flowbio <resource> <verb>`).
- **Rationale**: FR-039/FR-040 require fast on-demand cold starts under
  `uvx --from "flowbio==X.Y.Z"` and a lean install closure. `argparse` is
  stdlib, so it adds zero to the dependency closure and nothing to import time.
  It supports nested subparsers (resource → verb), per-command help (FR-003),
  and `--version` (FR-005) natively.
- **Alternatives rejected**:
  - *click* / *typer* — ergonomic, but each adds a runtime dependency (typer
    also pulls `click` + `rich`), enlarging the closure and slowing cold start
    for no capability this spec needs. Preferred against here on Principle V
    (YAGNI) and FR-040's lean-closure goal — not because dependencies are
    forbidden (FR-040 permits them with justification), but because none is
    warranted for this feature.

## 2. Global options accepted before *and* after the verb (FR-004)

- **Decision**: Define global options (`--json`, `--no-progress`, `--token`,
  `--token-file`, `--base-url`, `--login`, `--username`) on a shared
  `argparse` *parent parser* and attach that parent to **both** the top-level
  parser and every leaf subparser. Merge the two namespaces (a value set on
  either side wins; if neither, the default applies).
- **Rationale**: argparse does not natively interleave a parent's optionals
  after positionals consumed by a subparser. Registering the same options on the
  leaf subparser makes `flowbio --json samples upload …` and
  `flowbio samples upload … --json` produce identical results, satisfying FR-004
  and the edge case in the spec.
- **Alternatives rejected**:
  - Single top-level-only globals — fails FR-004 (options after the verb would
    error).
  - `parse_known_args` + manual re-parse — more code, more edge cases; rejected
    on Principle V.

## 3. Credential resolution & precedence (FR-006…FR-013)

- **Decision**: A single `_auth.resolve_credentials(...)` builds a
  `flowbio.v2.auth.Credentials` from CLI inputs with precedence:
  **forced login (`--login`) → direct token (`--token` / `FLOW_API_TOKEN`) →
  token file (`--token-file` / `FLOW_TOKEN_FILE`) → default token file
  (`~/.config/flow/api-token`) → username/password prompt**. For token and
  base-URL, explicit flag > environment variable > default.
- **Prompts**: username via `input()`, password via `getpass.getpass()` (never a
  flag/env — FR-008, Principle VI). Before prompting, check
  `sys.stdin.isatty()`; if not a TTY, fail fast with exit code 2 and an
  actionable message (FR-012, SC-003).
- **Errors**: explicitly named token file missing/empty → usage error (FR-010);
  `--token` together with `--login` → usage error (FR-011).
- **Rationale**: Centralizing precedence keeps each rule testable in isolation
  and mirrors the v2 `Credentials` strategy already in the library — the CLI
  constructs `TokenCredentials` or `UsernamePasswordCredentials` and calls
  `client.log_in(...)`, adding no auth protocol of its own.
- **Alternatives rejected**: persisting a token after username/password login —
  explicitly out of scope in the spec; would also touch Principle VI.

## 4. Output modes and clean stdout under `--json` (FR-035…FR-037)

- **Decision**: An `_output` module with two render paths. Human mode writes
  concise lines to **stdout** for results and to **stderr** for advisory text
  (e.g. the `batch-template` required-columns summary, FR-025). `--json` mode
  writes exactly one `json.dumps(...)` document to stdout and nothing else
  there; errors under `--json` become a JSON document on **stderr** carrying
  message and status code where applicable (FR-037).
- **Rationale**: Keeping stdout clean lets agents pipe `--json` straight into a
  parser (SC-002). Routing progress and advisories to stderr is what makes that
  possible.
- **Alternatives rejected**: a logging framework — overkill; stdout/stderr
  discipline plus `print` is sufficient and clearer (Principle V).

## 5. Progress display (FR-036)

- **Decision**: Reuse the library's existing progress (tqdm via
  `ClientConfig.show_progress`), which already renders to stderr. `--no-progress`
  sets `ClientConfig(show_progress=False)` and suppresses any CLI-side spinners.
- **Rationale**: No new mechanism; tqdm already writes to stderr, satisfying the
  clean-stdout requirement, and it is already a declared dependency.
- **Alternatives rejected**: a second progress library — redundant; Principle V.

## 6. Exit-code contract (FR-038)

- **Decision**: An `ExitCode` IntEnum — `0` success, `1` API/runtime (incl. a
  batch with any failed upload), `2` usage/config/input (incl. batch pre-flight
  failure and a non-CSV sheet), `3` auth failed, `4` not found, `5` bad
  request/validation — plus a `_exit_codes.exit_code_for(exc)` mapping from the
  `FlowApiError` hierarchy: `AuthenticationError→3`, `NotFoundError→4`,
  `BadRequestError`/`AnnotationValidationError→5`, other `FlowApiError→1`.
- **Rationale**: A single mapping table keeps codes stable and documented so
  callers can branch (SC-002). Mapping lives in one place per Principle II.
- **Alternatives rejected**: ad-hoc `sys.exit(n)` scattered through handlers —
  unstable and untestable; rejected.

## 7. Sample-sheet format & parsing (FR-020…FR-023, FR-027…FR-031)

- **Decision**: CSV only, parsed with the stdlib `csv` module. Reserved columns
  `name`, `reads1`, `reads2`, `project`, `organism`; every other header is a
  metadata-attribute identifier (with `<id>__annotation` companions). Reads paths
  resolve relative to the **sheet file's directory** (absolute paths as-is).
  Non-CSV inputs (`.xlsx`, `.tsv`) are rejected up front with an "export to CSV"
  message and exit code 2. The whole sheet is parsed and every row validated
  before any upload (FR-027).
- **Detection**: CSV is the only accepted format (clarification 2026-06-05); a
  `.xlsx`/`.tsv` suffix (or a sheet that does not parse as comma-delimited) is
  rejected — the CLI does not attempt TSV sniffing.
- **Rationale**: CSV matches `batch-template` output; stdlib `csv` needs no
  dependency (FR-040). Validating up front (all errors at once, nothing
  uploaded) delivers SC-005.
- **Alternatives rejected**: `pandas`/`openpyxl` for Excel — out of scope
  (CSV-only per the clarification) and a heavy dependency we chose to avoid to
  keep the closure lean (FR-040 would permit it if a future need justified it).

## 8. Sequential batch upload semantics (FR-030)

- **Decision**: Upload rows one at a time in sheet order via repeated
  `client.samples.upload_sample(...)`. Default: continue past per-row failures,
  recording each; exit 1 if any failed. `--stop-on-error`: abort on the first
  failing row (earliest in order), reporting already-uploaded rows.
- **Rationale**: Matches the clarified semantics; "first failure" is
  deterministic in row order. No concurrency keeps reporting and `--stop-on-error`
  unambiguous (Principle V).
- **Alternatives rejected**: concurrent upload — clarified against; would make
  "first failure" non-deterministic.

## 9. Metadata input: `--metadata key=value` + `--metadata-json` (FR-018, FR-019)

- **Decision**: Accept repeated `--metadata key=value` (split on the **first**
  `=` only) and a single `--metadata-json '{…}'`; merge both into one dict. A key
  present in both is a usage error (exit 2). Annotation companions are ordinary
  keys of the form `<identifier>__annotation`, passed through unchanged.
- **Rationale**: Repeated pairs suit humans; a JSON object suits agents passing a
  dict without shell-quoting (spec rationale). First-`=` split handles values
  containing `=` (spec edge case).
- **Alternatives rejected**: last-write-wins merge — silently hides conflicts;
  the spec mandates a usage error.

## 10. Library prerequisite — expose "allows annotation" on MetadataAttribute

- **Decision**: Add an additive boolean field to
  `flowbio.v2.samples.MetadataAttribute` indicating whether the attribute permits
  a free-text annotation, populated from the existing `/samples/metadata`
  response in `_create_metadata_attribute`. `batch-template` uses it to emit
  `<identifier>__annotation` companion columns (FR-024) and the per-column JSON
  description (FR-026).
- **Open detail (low risk)**: the exact raw response key for annotation support
  is confirmed against the live `/samples/metadata` payload during
  implementation (the spec's lone library dependency). The field is additive and
  defaults conservatively (no annotation) if absent, so the change is
  backwards-compatible regardless (Principle VII). This is the only library
  change the feature requires.
- **Rationale**: Keeping the knowledge of annotation support in the library
  (not hard-coded in the CLI) honours "the backend is the source of truth" and
  Principle II (the CLI adds no protocol logic).
- **Alternatives rejected**: hard-coding which attributes allow annotation in the
  CLI — brittle and a layering violation.

## 11. Distribution as a console script (FR-039, FR-040)

- **Decision**: Register `console_scripts` entry point
  `flowbio = flowbio.cli._main:main` in `setup.py`. Verify resolution via
  `uvx --from "flowbio==X.Y.Z" flowbio --version`.
- **Rationale**: A console-script entry point is the standard, install-location-
  independent way to expose a command and is what `uvx` resolves (SC-006).
- **Alternatives rejected**: a top-level script file — not resolvable via
  `uvx --from` without an entry point; rejected.

## 12. Testing approach

- **Decision**: In-process tests invoke `_main.main(argv)` (or per-command
  handlers) with explicit argv, capture stdout/stderr (via `capsys`) and the
  returned/raised exit code, and mock HTTP with `respx` (the existing stack).
  A shared `conftest.py` helper provides the runner.
- **Rationale**: In-process invocation is fast and lets each behavior be driven
  test-first (Principle I) without subprocess overhead. `respx` is already the
  project's HTTP mock.
- **Alternatives rejected**: subprocess-based CLI tests — slower, harder to
  assert on, and unnecessary for argparse handlers.

## 13. `annotation-template` download and its (non-)relationship to `batch-template` (FR-043, FR-044)

- **Decision**: `samples annotation-template` wraps the **existing**
  `client.samples.get_annotation_template(sample_type) -> bytes`, writing the
  returned server-generated `.xlsx` workbook to `-o/--output` verbatim. No
  library change is needed (contrast item 10). `--sample-type` is optional and
  defaults to `"generic"`. Because the body is binary, the command refuses to
  write to a terminal stdout (exit `2`); under `--json` it emits a small
  `{output, sample_type}` document instead.
- **Investigated**: whether the annotation sheet could double as the
  `batch-template` CSV (or vice versa). It cannot. Per the flow-api source
  (`api/samples/annotation.py::build_annotation_template_dataframe`,
  `api/samples/views.py::annotation`), the annotation sheet is an Excel workbook
  keyed by metadata-attribute *display names* (with a ` (Required)` suffix),
  carrying `Type`, `File`, `Sample Name`, `Project Name`, `Organism`, and
  `PubMed ID` columns; the batch sheet is a CLI-built CSV keyed by attribute
  *identifiers* with `reads1`/`reads2` columns and no `Type` column. Neither
  feeds the other unchanged, so the two template commands stay distinct.
- **Rationale**: Reusing the existing library method keeps the CLI a thin
  presentation layer (Principle II) and avoids a second library change. Treating
  the workbook as opaque bytes (no CLI-side parsing) keeps the command simple
  (Principle V) and honours the backend as the source of truth for the sheet's
  shape.
- **Alternatives rejected**: (a) generating the annotation sheet CLI-side from
  metadata attributes — duplicates server logic and would drift; (b) translating
  the annotation sheet into the batch CSV (or vice versa) — out of scope and
  fragile given the divergent column contracts.
