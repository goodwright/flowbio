# Feature Specification: flowbio Command-Line Interface

**Feature Branch**: `001-flowbio-cli`

**Created**: 2026-06-05

**Status**: Draft

**Input**: User description: "Translate the flow-cli-spec.md into a new feature specification. Ignore certain technical details as appropriate, but preserve the overall public functionality."

## Overview

Today the flowbio library can only be used by writing Python that constructs a client and calls
its upload methods. This feature adds a command named **`flowbio`** that lets a person — or an
automated agent acting on their behalf — perform the library's upload operations directly from the
command line, without writing any code.

Commands are grouped by the kind of thing they act on (`flowbio data …` for generic files,
`flowbio samples …` for samples), so the command surface reads the same way the library does. Every
command works both for a human reading concise messages in a terminal and for an automated caller
that needs structured, parseable output and stable exit codes to branch on.

## Clarifications

### Session 2026-06-05

- Q: What are the environment variable names for the token, token-file path, and base URL? → A: `FLOW_API_TOKEN`, `FLOW_TOKEN_FILE`, `FLOW_API_URL`
- Q: How should the CLI detect a sample sheet's format (CSV vs TSV)? → A: Accept CSV only for now — it matches the `batch-template` output format; TSV is not supported
- Q: Should the CLI pre-validate `--sample-type`/`--data-type` against the server before uploading? → A: No — send the type and surface the server's rejection (backend is source of truth); an invalid type returns the bad-request exit code
- Q: What happens when `data upload` is run without `--data-type`? → A: `--data-type` is optional; when omitted no data type is sent and the library/server applies its own default/inference
- Q: Does `upload-batch` upload rows sequentially or concurrently? → A: Sequentially, in sheet row order (one row at a time); "first failure" for `--stop-on-error` means the first failing row in order

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Upload a generic data file from the command line (Priority: P1)

A researcher (or an automated agent) has a file on disk — a counts table, a reference, an archive —
and wants to upload it to Flow without opening a Python session. They run a single command, pointing
it at the file, and get back the identifier of the uploaded data.

This story also establishes the foundations every other command reuses: authentication, output
formatting (human and machine-readable), progress display, and the exit-code contract.

**Why this priority**: It is the smallest end-to-end slice that proves the whole command works —
parsing, credential resolution, calling the library, rendering a result, and returning an exit code.
It is independently useful on its own and unblocks every later command.

**Independent Test**: Run `flowbio data upload ./counts.tsv` with a valid token against a test
backend; confirm the file is uploaded and the returned data identifier is printed, exit code `0`.
Re-run with `--json` and confirm a single structured document is printed to standard output.

**Acceptance Scenarios**:

1. **Given** a valid token and a readable file, **When** the user runs `flowbio data upload PATH`,
   **Then** the file is uploaded and a confirmation with the data identifier is printed, exit `0`.
2. **Given** the same, **When** the user adds `--json`, **Then** a single JSON document containing
   the data identifier is printed to standard output and nothing else.
3. **Given** a file whose name the user wants to override, **When** they pass `--filename NAME`,
   **Then** the stored name is `NAME`.
4. **Given** an archive, **When** the user passes `--directory`, **Then** it is uploaded as a
   directory archive.
5. **Given** the server rejects the request (e.g. a bad data type), **When** the upload runs,
   **Then** the error message is shown on standard error and the exit code reflects "bad request".
6. **Given** an invalid token, **When** any command runs, **Then** the exit code reflects
   "authentication failed" and the error is surfaced clearly.

---

### User Story 2 - Upload a single sequencing sample (Priority: P2)

A user has one demultiplexed sample — either a single reads file or a paired-end pair — together
with a sample name, a sample type, and optional metadata. They want to upload it as a sample in one
command, supplying metadata either as repeated `key=value` pairs or as a single JSON object (the
latter so an agent can pass a dictionary it already holds without shell-quoting).

**Why this priority**: Samples are the core domain object; single-sample upload is the most common
manual task and is the per-sample building block the batch flow reuses.

**Independent Test**: Run `flowbio samples upload --name s1 --sample-type rna_seq --reads1 r1.fq.gz`
against a test backend; confirm the sample is created and its identifier is printed. Repeat with
`--reads2` for paired-end and with `--metadata` / `--metadata-json` for metadata.

**Acceptance Scenarios**:

1. **Given** a name, sample type, and one reads file, **When** the user runs `flowbio samples
   upload`, **Then** a single-ended sample is created and its identifier is printed, exit `0`.
2. **Given** two reads files, **When** the user adds `--reads2`, **Then** a paired-end sample is
   created.
3. **Given** metadata as repeated `--metadata key=value` flags, **When** the sample uploads,
   **Then** each pair is sent as a metadata attribute keyed by its identifier.
4. **Given** metadata as `--metadata-json '{…}'`, **When** the sample uploads, **Then** the JSON
   object is used as the metadata.
5. **Given** the same key supplied via both `--metadata` and `--metadata-json`, **When** the command
   runs, **Then** it fails with a usage error before uploading.
6. **Given** an attribute that carries a free-text annotation, **When** the user passes both the
   value and its `<identifier>__annotation` companion, **Then** both are sent as metadata.

---

### User Story 3 - Generate a sample-sheet template (Priority: P3)

Before uploading many samples, a user wants a correctly-shaped, empty sample sheet to fill in. They
ask for a template for a given sample type and receive a header row listing the columns the batch
upload expects: the reserved columns (sample name, reads files, project, organism) followed by one
column per metadata attribute. They are told which columns are required for that sample type.

**Why this priority**: The template defines the contract for batch upload (Story 4); producing it
correctly is a prerequisite for users to author valid sheets.

**Independent Test**: Run `flowbio samples batch-template --sample-type rna_seq` and confirm a CSV
header with the reserved columns and metadata-attribute columns is produced, plus a summary of which
columns are required for `rna_seq`.

**Acceptance Scenarios**:

1. **Given** a sample type, **When** the user runs `flowbio samples batch-template --sample-type T`,
   **Then** a CSV header row of reserved columns followed by metadata-attribute columns is produced
   (there is no `sample_type` column).
2. **Given** the same, **When** run without `--json`, **Then** a human-readable summary of which
   columns are required versus optional for `T` is shown on standard error.
3. **Given** `-o/--output PATH`, **When** the command runs, **Then** the template is written to that
   file instead of standard output.
4. **Given** an attribute that allows a free-text annotation, **When** the template is generated,
   **Then** a companion `<identifier>__annotation` column is included.
5. **Given** `--json`, **When** the command runs, **Then** a structured description of every column
   (its name, whether it is reserved/metadata/annotation, whether it is required, and any closed
   list of allowed values) is produced and no CSV is printed — so an agent can build rows directly.
6. **Given** no `--sample-type`, **When** the command runs, **Then** it fails with a usage error.

---

### User Story 4 - Upload a batch of samples from a sample sheet (Priority: P4)

A user has filled in a sample sheet (CSV) with one demultiplexed sample per row — reads
paths plus metadata — and wants to upload them all in one command, applying a single sample type to
every row. Before any upload happens, every row is validated; nothing should fail silently.

**Why this priority**: Batch upload is the highest-leverage workflow for real datasets, but it
depends on the per-sample path (Story 2) and the sheet contract (Story 3).

**Independent Test**: Author a two-row CSV and run `flowbio samples upload-batch --sheet x.csv
--sample-type rna_seq`; confirm both rows are validated then uploaded, with a final summary of how
many succeeded, failed, and were skipped.

**Acceptance Scenarios**:

1. **Given** a valid sheet and a sample type, **When** the user runs `flowbio samples upload-batch`,
   **Then** every row is uploaded with the given sample type applied uniformly, exit `0`.
2. **Given** relative reads paths in the sheet, **When** the batch runs, **Then** paths resolve
   relative to the sheet file's location (absolute paths are used as-is).
3. **Given** any invalid row (missing required value, missing reads file on disk, a space in the
   name, a value outside an attribute's allowed list, a required-for-type metadata missing, or an
   annotation set with no corresponding value), **When** the command runs, **Then** all per-row
   errors are reported with their row number and sample name, and nothing is uploaded, exit
   "usage/input error".
4. **Given** invalid rows and `--skip-invalid`, **When** the command runs, **Then** the invalid rows
   are skipped (and reported with reasons) and the valid rows are uploaded.
5. **Given** a row whose upload fails at the server, **When** the default behaviour applies, **Then**
   the run continues, the failure is reported with row number, name, and message, and the run exits
   with an "API/runtime error" code; with `--stop-on-error` the run aborts on the first failure and
   already-uploaded rows are reported.
6. **Given** `--json`, **When** the batch finishes, **Then** a single document with `uploaded`,
   `failed`, and `skipped` lists plus a `counts` summary is produced.
7. **Given** a non-CSV file (e.g. an Excel `.xlsx` or a `.tsv`) is passed as the sheet, **When** the
   command runs, **Then** it fails with a clear "export to CSV" message (CSV only).

---

### User Story 5 - Upload multiplexed reads with an annotation sheet (Priority: P5)

A user has a multiplexed reads file (optionally paired-end) plus an annotation sheet that the
backend uses to demultiplex it server-side. They want to submit both in one command and see the
resulting data identifiers, the annotation identifier, and any warnings the server raised.

**Why this priority**: It completes the upload surface but is the least common manual flow and is
independent of the others.

**Independent Test**: Run `flowbio samples upload-multiplexed --reads1 r1.fq.gz --annotation
sheet.csv`; confirm the data identifiers, annotation identifier, and any warnings are reported.

**Acceptance Scenarios**:

1. **Given** a reads file and an annotation sheet, **When** the user runs `flowbio samples
   upload-multiplexed`, **Then** the upload is submitted and the resulting identifiers (and any
   warnings) are reported, exit `0`.
2. **Given** `--reads2`, **When** the command runs, **Then** the reads are treated as paired-end.
3. **Given** annotation warnings, **When** the default behaviour applies, **Then** warnings are
   reported but the upload proceeds; with `--reject-warnings` warnings cause the upload to be
   rejected.
4. **Given** the annotation sheet fails server validation, **When** the command runs, **Then** the
   validation errors are surfaced and the exit code reflects "bad request".

---

### Edge Cases

- **No authentication provided**: the default token file location is checked; if it holds a
  non-empty token that is used, otherwise the user is prompted for username and password.
- **A specific token file is requested but missing or empty**: this is an error (the user named a
  file), not a silent fall-through to a prompt.
- **A prompt would be needed but the command is not running interactively** (a pipe, CI, an agent):
  the command fails fast with a clear message instead of hanging, so non-interactive callers must
  supply a token.
- **Conflicting authentication flags** (a direct token together with forcing interactive login):
  treated as a usage error.
- **No resource or no command given** (e.g. bare `flowbio`, or `flowbio data` with no verb): help is
  shown and a usage exit code is returned.
- **Global options before or after the verb**: `flowbio --json samples upload …` and `flowbio
  samples upload … --json` behave identically.
- **Metadata `key=value` containing `=` in the value**: only the first `=` separates key from value.
- **Empty metadata cells in a sample sheet**: omitted entirely rather than sent as empty values.

## Requirements *(mandatory)*

### Functional Requirements

#### Command surface

- **FR-001**: The system MUST provide a single command named `flowbio` with resource-namespaced
  subcommands of the form `flowbio <resource> <verb>`.
- **FR-002**: The system MUST provide these commands: `data upload`, `samples upload`, `samples
  batch-template`, `samples upload-batch`, and `samples upload-multiplexed`.
- **FR-003**: The system MUST provide help at the top level, per resource group, and per command,
  and MUST return a usage exit code when no resource or no verb is supplied or an unknown one is
  given.
- **FR-004**: Global options MUST be accepted both before and after the verb with identical effect.
- **FR-005**: `flowbio --version` MUST print the installed version and exit successfully.

#### Authentication

- **FR-006**: When no authentication option is given, the system MUST read a token from the default
  token file location (`~/.config/flow/api-token`) if it exists and is non-empty, otherwise fall
  back to a username/password prompt.
- **FR-007**: The system MUST allow a token to be supplied directly (`--token`, or the
  `FLOW_API_TOKEN` environment variable) and MUST allow a token file path to be supplied
  (`--token-file`, or the `FLOW_TOKEN_FILE` environment variable).
- **FR-008**: The system MUST allow forcing an interactive username/password login, prompting for
  the password (the password MUST NEVER be accepted as a flag or environment variable).
- **FR-009**: Credential resolution precedence MUST be: forced login → direct token → token file →
  username/password prompt; for token and base-URL settings, an explicit flag MUST take precedence
  over an environment variable, which takes precedence over the default.
- **FR-010**: If an explicitly named token file is missing or empty, the system MUST fail with a
  usage/configuration error rather than silently prompting.
- **FR-011**: Supplying both a direct token and forced interactive login MUST be a usage error.
- **FR-012**: If a prompt would be required but the session is not interactive, the system MUST fail
  fast with a clear message instructing the caller to supply a token, rather than blocking on input.
- **FR-013**: The system MUST allow the Flow API base URL to be overridden (`--base-url`, or the
  `FLOW_API_URL` environment variable).

#### `data upload`

- **FR-014**: `data upload PATH` MUST upload the file at `PATH` and report the resulting data
  identifier; `--filename` MUST override the stored name and `--data-type` MUST set the data type.
  `--data-type` MUST be optional; when omitted, no data type is sent and the library/server applies
  its own default or inference. The CLI MUST NOT pre-validate `--data-type`; an unknown value is sent
  as-is and the server's rejection surfaces via the bad-request exit code.
- **FR-015**: `data upload --directory` MUST upload the file as a directory archive.

#### `samples upload`

- **FR-016**: `samples upload` MUST require a sample name, a sample type, and a first reads file, and
  MUST accept an optional second reads file for paired-end samples. The CLI MUST NOT pre-validate the
  sample type against the server's known list; an unknown type is sent as-is and the server's
  rejection surfaces via the bad-request exit code.
- **FR-017**: `samples upload` MUST accept an optional project identifier and organism identifier.
- **FR-018**: Metadata MUST be accepted both as repeated `--metadata key=value` pairs (split on the
  first `=`) and as a single `--metadata-json` object of identifier→value; the two MUST be merged,
  and a key supplied by both MUST be a usage error.
- **FR-019**: Free-text annotation companions to metadata values MUST be expressible as ordinary
  metadata keys of the form `<identifier>__annotation` and passed through unchanged.

#### Sample sheet (`batch-template` and `upload-batch`)

- **FR-020**: A sample sheet MUST be a CSV (comma-delimited) file with one sample per row, matching
  the format produced by `batch-template`; non-CSV files (e.g. Excel `.xlsx`, or tab-delimited
  `.tsv`) MUST be rejected with a clear "export to CSV" message.
- **FR-021**: The sheet's reserved columns MUST be `name` (required), `reads1` (required), `reads2`,
  `project`, and `organism`; the sample type MUST NOT be a column — it is supplied once via
  `--sample-type` and applied to every row.
- **FR-022**: Every non-reserved column header MUST be treated as a metadata attribute identifier,
  with each cell becoming that row's value for the attribute; empty cells MUST be omitted.
- **FR-023**: Reads paths in the sheet MUST resolve relative to the sheet file's directory; absolute
  paths MUST be used as-is.
- **FR-024**: `samples batch-template --sample-type T` MUST produce a header row of the reserved
  columns followed by one column per metadata attribute, plus a `<identifier>__annotation` column
  for each attribute that allows annotation, and MUST support writing to a file via `-o/--output`.
- **FR-025**: `samples batch-template` MUST report which columns are required for the chosen sample
  type (a metadata attribute is required when it is globally required or required for that sample
  type); without `--json` this summary goes to standard error, and `--sample-type` MUST be required.
- **FR-026**: `samples batch-template --json` MUST produce a structured per-column description
  (name; whether the column is reserved, metadata, or annotation; required flag; allowed-value list
  where the attribute has a closed set; and a description) and MUST NOT print a CSV.

#### `upload-batch`

- **FR-027**: `samples upload-batch` MUST require `--sheet` and `--sample-type`, parse the entire
  sheet up front, and validate every row before any upload occurs.
- **FR-028**: Pre-flight validation MUST check, per row: required reserved values present; required
  metadata for the sample type present; reads files exist on disk; the name contains no spaces;
  values for attributes with a closed allowed-value list are within that list; and an annotation
  companion is only set when its value is also set and only for annotation-enabled attributes.
- **FR-029**: If any row fails validation, the system MUST report all per-row errors (each with its
  1-based row number and sample name) and MUST upload nothing, returning a usage/input exit code;
  `--skip-invalid` MUST instead skip invalid rows (reporting them with reasons) and upload the rest.
- **FR-030**: Rows MUST be uploaded sequentially, in sheet row order (one row at a time). During
  upload, the system MUST by default continue past per-row upload failures, recording each against
  its row; `--stop-on-error` MUST abort on the first failing row (the earliest in row order) while
  preserving and reporting already-uploaded rows.
- **FR-031**: Every validation error and upload failure MUST be surfaced with its row number, sample
  name, and the underlying message — nothing fails silently.
- **FR-032**: `samples upload-batch --json` MUST produce a single document containing `uploaded`,
  `failed`, and `skipped` lists and a `counts` summary.

#### `upload-multiplexed`

- **FR-033**: `samples upload-multiplexed` MUST require a first reads file and an annotation sheet,
  accept an optional second reads file, and report the resulting data identifiers, annotation
  identifier, and any warnings.
- **FR-034**: By default annotation warnings MUST be reported but not block the upload;
  `--reject-warnings` MUST cause warnings to reject the upload.

#### Output and exit codes

- **FR-035**: Each command MUST support a human-readable mode (default, concise lines on standard
  output) and a `--json` mode that emits a single machine-readable document on standard output and
  nothing else there.
- **FR-036**: Progress indication MUST be shown on standard error (so `--json` output on standard
  output stays clean) and MUST be disable-able via `--no-progress`.
- **FR-037**: Errors MUST be written to standard error; under `--json` the error MUST also be a JSON
  document on standard error carrying the message and a status code where applicable.
- **FR-038**: The system MUST return documented, stable exit codes so callers can branch on failure
  type: `0` success; `1` API/runtime error (including a batch with any failed uploads); `2`
  usage/configuration/input error (including batch pre-flight failure and a passed Excel sheet); `3`
  authentication failed; `4` not found; `5` bad request / validation error.

#### Distribution

- **FR-039**: The `flowbio` command MUST be installable as a console script and resolvable on demand
  from the published package, pinned to an exact version, in an ephemeral isolated environment
  (e.g. `uvx --from "flowbio==X.Y.Z" flowbio …`), without relying on a global install, the working
  directory, or local source.
- **FR-040**: Adding runtime dependencies is permitted, not prohibited: the team MAY add a
  dependency where it improves the implementation. Any dependency the feature adds MUST install from
  the published package into the ephemeral isolated environment of FR-039, and the install closure
  SHOULD be kept lean so on-demand cold starts stay fast.

#### Documentation

- **FR-041**: The feature MUST ship user-facing documentation covering the command surface (each
  command and its options), the authentication resolution order, the exit-code contract, the
  human-vs-`--json` output modes, and the sample-sheet schema (reserved columns, metadata-identifier
  columns, annotation companions, relative-path resolution), with at least one worked usage example
  per command.
- **FR-042**: Documentation MUST be delivered alongside the commands it describes (a command is not
  complete until its documentation lands), so the documented surface never lags the shipped surface.

### Key Entities *(include if feature involves data)*

- **Data file**: A generic file uploaded to Flow; identified by a returned data identifier; may be a
  single file or a directory archive, with an optional stored name and data type.
- **Sample**: A named, typed biological sample with one or two reads files, optional metadata,
  project, and organism; identified by a returned sample identifier.
- **Metadata attribute**: A named property a sample can carry, keyed by a stable identifier; may be
  globally required or required only for certain sample types; may have a closed set of allowed
  values; may permit an additional free-text annotation.
- **Sample sheet**: A CSV table of demultiplexed samples (one per row) with reserved columns
  (name, reads files, project, organism) and metadata-identifier columns.
- **Annotation sheet**: A file submitted alongside multiplexed reads that the backend uses to
  demultiplex them server-side.
- **Credentials**: Either a token (supplied directly, from a file, or from an environment variable)
  or a username/password pair entered interactively.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A user can upload a single data file with one command and, on success, see its
  identifier — without writing any code.
- **SC-002**: An automated caller can run any command with `--json`, parse a single structured
  document from standard output, and branch on the documented exit code without scraping
  human-readable text.
- **SC-003**: A non-interactive caller that supplies a valid token never blocks on a prompt; one
  that supplies no token fails immediately with an actionable message rather than hanging.
- **SC-004**: For a batch upload, a user can determine for every input row whether it was uploaded,
  failed, or skipped, and why — with no row outcome left unreported.
- **SC-005**: Given an invalid sample sheet, the user receives every row's validation error in one
  run and no samples are uploaded, so they can fix all problems before retrying.
- **SC-006**: The command can be run on a machine with no prior flowbio install, pinned to an exact
  version, in an ephemeral environment, and works using only its arguments and environment.
- **SC-007**: All five commands (data upload, single sample, batch template, batch upload,
  multiplexed upload) are usable end-to-end, each independently demonstrable.
- **SC-008**: A new user can, from the documentation alone, run every command correctly — including
  authenticating, choosing human vs `--json` output, interpreting an exit code, and authoring a
  valid sample sheet — without reading the source.

## Assumptions

- The underlying library already provides the upload operations the commands wrap (generic data
  upload, single demultiplexed sample upload, multiplexed upload) and the read-only lookups needed
  to build templates and validate sheets (metadata attributes, sample types, organisms, projects);
  the CLI is a presentation layer over them and adds no protocol logic of its own.
- Whether a metadata attribute permits a free-text annotation is information the CLI can obtain from
  the library; exposing that fact is a small additive prerequisite for the template command and is
  the only library change this feature depends on.
- The default token file location is `~/.config/flow/api-token`, matching existing flow tooling.
- Sample names contain no spaces (the backend rejects them); the CLI surfaces this as an early
  validation rather than relying solely on a server rejection.
- The backend remains the source of truth for validation; the CLI's pre-flight checks are a
  friendly early filter, not a replacement for server-side validation.
- Out of scope for this feature: non-sequencing single-sample uploads with arbitrary data keys;
  Excel sample sheets; reusing the server's downloaded annotation-sheet headers for the batch sheet;
  read-only discovery commands; and persisting a token after a username/password login.
