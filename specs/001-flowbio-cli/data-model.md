# Phase 1 Data Model: flowbio CLI

The CLI is a presentation layer; most domain entities already exist as frozen
`flowbio.v2` Pydantic models and are reused as-is. This document captures the
entities the CLI introduces or extends, their fields, validation rules, and
state transitions. Field-by-field command I/O lives in [contracts/](./contracts/).

## Reused library entities (no change)

| Entity | Source | Used by |
|--------|--------|---------|
| `Data` (`id`) | `flowbio.v2.data` | `data upload` result |
| `Sample` (`id`) | `flowbio.v2.samples` | `samples upload`, `upload-batch` rows |
| `MultiplexedUpload` (`data_ids`, `annotation_id`, `warnings`) | `flowbio.v2.samples` | `upload-multiplexed` result |
| `SampleType` (`identifier`, `name`, `description`) | `flowbio.v2.samples` | `batch-template` (type validation surfaced by server) |
| `Project`, `Organism` | `flowbio.v2.samples` | reserved-column values (passed through) |

## Extended library entity (additive change)

### `MetadataAttribute` (`flowbio.v2.samples`)

Existing fields: `identifier`, `name`, `description`, `required`,
`required_for_sample_types: list[str]`, `options: list[str] | None`.

**Added field** (the feature's only library change):

| Field | Type | Description |
|-------|------|-------------|
| `allows_annotation` | `bool` | Whether this attribute permits a free-text annotation companion. Drives the `<identifier>__annotation` columns and JSON descriptors in `batch-template`. |

Rules:
- Populated from the `/samples/metadata` response in `_create_metadata_attribute`.
- Additive and backwards-compatible: defaults to `False` when the raw payload
  omits the source key (Principle VII).
- "Required for a chosen sample type" (used by `batch-template`) is derived, not
  stored: an attribute is required when `required is True` **or** the chosen
  `--sample-type` is in `required_for_sample_types`.

## CLI-introduced entities

These are internal (`_`-prefixed) value objects used between parsing, validation,
rendering, and exit. They are not part of the library's public API.

### `ExitCode` (IntEnum) — `flowbio/cli/_exit_codes.py`

| Name | Value | Meaning (FR-038) |
|------|-------|------------------|
| `SUCCESS` | 0 | Success |
| `RUNTIME` | 1 | API/runtime error; batch with any failed upload |
| `USAGE` | 2 | Usage/config/input error; batch pre-flight failure; non-CSV sheet |
| `AUTH` | 3 | Authentication failed |
| `NOT_FOUND` | 4 | Not found |
| `BAD_REQUEST` | 5 | Bad request / validation error |

Mapping `exit_code_for(exc)`:
`AuthenticationError→AUTH`, `NotFoundError→NOT_FOUND`,
`BadRequestError`/`AnnotationValidationError→BAD_REQUEST`,
other `FlowApiError→RUNTIME`, usage/validation raised by the CLI →`USAGE`.

### `ResolvedCredentials` (selection result) — `flowbio/cli/_auth.py`

Not a stored model — `resolve_credentials(...)` returns a
`flowbio.v2.auth.Credentials` (`TokenCredentials` or
`UsernamePasswordCredentials`) plus the resolved base URL. Inputs and precedence:

| Source | Precedence (highest first) |
|--------|----------------------------|
| `--login` (force username/password) | 1 |
| `--token` / `FLOW_API_TOKEN` | 2 |
| `--token-file` / `FLOW_TOKEN_FILE` | 3 |
| default token file `~/.config/flow/api-token` | 4 |
| username/password prompt | 5 (fallback) |

Base URL: `--base-url` > `FLOW_API_URL` > library default.

Validation rules:
- `--token` **and** `--login` together → `USAGE`.
- Explicitly named token file missing/empty → `USAGE` (not a silent prompt).
- A prompt needed but `stdin` is not a TTY → `USAGE`, fail fast.
- Password never sourced from a flag or environment variable.

### `MetadataInput` (parsed) — `flowbio/cli/samples.py`

Merged result of `--metadata key=value` (repeated) and `--metadata-json`:

| Aspect | Rule |
|--------|------|
| key/value split | on the **first** `=` only (value may contain `=`) |
| JSON object | identifier→value mapping |
| merge | union of both inputs |
| conflict | same key in both sources → `USAGE` error before upload |
| annotation companion | key of form `<identifier>__annotation`, passed through unchanged |

### `SampleSheet` and `SheetRow` — `flowbio/cli/_sheet.py`

Parsed representation of a CSV sample sheet.

`SampleSheet`:
| Field | Type | Notes |
|-------|------|-------|
| `path` | `Path` | sheet file location; reads paths resolve relative to its directory |
| `reserved_columns` | fixed set | `name` (req), `reads1` (req), `reads2`, `project`, `organism` |
| `metadata_columns` | `list[str]` | every non-reserved header = a metadata identifier (incl. `<id>__annotation`) |
| `rows` | `list[SheetRow]` | one per data row |

`SheetRow` (1-based `row_number`, `name`, resolved `reads1`/`reads2` paths,
optional `project`/`organism`, `metadata: dict`).

Per-row pre-flight validation (FR-028), all errors collected before any upload:
- required reserved values present (`name`, `reads1`);
- required metadata for the chosen sample type present;
- `reads1`/`reads2` files exist on disk (after relative-path resolution);
- `name` contains no spaces;
- values for closed-option attributes are within `options`;
- a `<id>__annotation` is set only when `<id>`'s value is set **and** the
  attribute `allows_annotation`;
- empty cells omitted (not sent as empty values).

### `BatchResult` — `flowbio/cli/samples.py`

Outcome of `upload-batch`, rendered to human text or the `--json` document
(FR-032):

| Field | Type | Notes |
|-------|------|-------|
| `uploaded` | `list[{row_number, name, sample_id}]` | succeeded rows |
| `failed` | `list[{row_number, name, message}]` | server/runtime failures |
| `skipped` | `list[{row_number, name, reasons}]` | `--skip-invalid` rows |
| `counts` | `{uploaded, failed, skipped}` | summary |

State transition for a row in a batch run:

```
parsed → validated ──(invalid, default)──→ ABORT whole run (nothing uploaded)
                   ──(invalid, --skip-invalid)──→ skipped
                   ──(valid)──→ upload ──(ok)──→ uploaded
                                         ──(error, default)──→ failed (run continues)
                                         ──(error, --stop-on-error)──→ ABORT (report uploaded so far)
```

Exit code: all uploaded → `SUCCESS`; any pre-flight invalid without
`--skip-invalid` → `USAGE`; any upload failure → `RUNTIME`.

### `BatchTemplate` descriptor — `flowbio/cli/samples.py`

For `batch-template` (FR-024…FR-026). Human mode emits a CSV header row +
required-columns summary on stderr. `--json` mode emits a per-column descriptor
list (no CSV):

| Per-column field | Notes |
|------------------|-------|
| `name` | column header |
| `kind` | `reserved` \| `metadata` \| `annotation` |
| `required` | reserved-required, or metadata required for the chosen type |
| `options` | closed allowed-value list, else `null` |
| `description` | from `MetadataAttribute.description` (reserved columns get a fixed blurb) |

Column order: reserved columns first (`name`, `reads1`, `reads2`, `project`,
`organism`), then one column per metadata attribute, each followed by its
`<identifier>__annotation` column when `allows_annotation`. There is **no**
`sample_type` column.
