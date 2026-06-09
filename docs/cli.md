# flowbio command-line interface

`flowbio` exposes the Flow upload operations from the terminal, for both humans
(concise lines) and automated agents (`--json` output with stable exit codes).
It is a thin layer over the `flowbio.v2` client — anything the CLI does, the
library can do programmatically.

```
flowbio <resource> <verb> [options]
flowbio --version
flowbio [--help | <resource> --help | <resource> <verb> --help]
```

Resources are `data` and `samples`. Run `flowbio --help`, `flowbio <resource>
--help`, or `flowbio <resource> <verb> --help` for self-documenting usage at
every level.

## Authentication

Credentials are resolved in this order (highest priority first):

1. `--login` — force an interactive username/password login.
2. `--token TOKEN`, or the `FLOW_API_TOKEN` environment variable — use this
   token directly.
3. `--token-file PATH`, or the `FLOW_TOKEN_FILE` environment variable — read the
   token from this file.
4. The default token file `~/.config/flow/api-token` — used **only when none of
   the above is supplied**.
5. An interactive username/password prompt (TTY only).

The base URL is resolved as `--base-url URL` > the `FLOW_API_URL` environment
variable > the library default (`https://app.flow.bio/api`). For both tokens and
the base URL, an explicit flag always beats the environment variable, which
beats the default.

The **password is only ever read from an interactive prompt** — never from a
flag or environment variable. If a prompt would be required but stdin is not a
terminal (e.g. in a non-interactive pipeline), the command fails fast with exit
code `2` rather than hanging.

A named token file (`--token-file`/`FLOW_TOKEN_FILE`) that is missing or empty,
and combining `--token` with `--login`, are both usage errors (exit `2`).

## Output modes

| Mode | stdout | stderr |
|------|--------|--------|
| Human (default) | concise result lines | progress, advisories, errors |
| `--json` | exactly one JSON document | a JSON error document on failure |

Under `--json`, stdout carries a single document and nothing else, so it can be
piped straight into a parser. On error, a JSON document is written to **stderr**
carrying `message` and, where applicable, a `status_code`.

Global options are accepted identically before *and* after the verb:
`flowbio --json data upload ./counts.tsv` and
`flowbio data upload ./counts.tsv --json` are equivalent.

Progress is shown on stderr during uploads; pass `--no-progress` to disable it.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | Success |
| `1` | API/runtime error (including a batch with any failed upload) |
| `2` | Usage / configuration / input error (including batch pre-flight failure, non-CSV sheet) |
| `3` | Authentication failed |
| `4` | Not found |
| `5` | Bad request / validation error |

The server is the source of truth: values such as `--data-type` are sent as-is
and validated server-side, surfacing as exit `5` on rejection.

## Commands

### `data upload`

Upload a generic data file.

```
flowbio data upload PATH [--filename NAME] [--data-type TYPE] [--directory]
```

Run `flowbio data upload --help` for the full option list. Note that
`--data-type` is sent as-is and validated server-side — the CLI does not
pre-check it.

**Output** — human: a confirmation line with the data identifier on stdout.
`--json`: `{"id": "<data_id>"}` on stdout.

**Exit codes** — `0` success; `5` server rejection (e.g. an unknown data type or
a filename containing spaces); `3` authentication failure; otherwise the
standard mapping above.

**Example**

```bash
$ flowbio data upload ./counts.tsv
Uploaded data data_xyz

$ flowbio data upload ./counts.tsv --json
{"id": "data_xyz"}
```

### `samples upload`

Upload a single demultiplexed sample — single-ended (`--reads1`) or paired-end
(add `--reads2`).

```
flowbio samples upload --name NAME --sample-type TYPE --reads1 PATH
    [--reads2 PATH] [--project ID] [--organism ID]
    [--metadata KEY=VALUE ...] [--metadata-json JSON]
```

Run `flowbio samples upload --help` for the full option list. The sample type is
sent as-is and validated server-side.

**Metadata** can be supplied two ways, which are merged:

- `--metadata KEY=VALUE`, repeatable. The split is on the **first** `=`, so a
  value may itself contain `=` (`--metadata formula=a=b+c`).
- `--metadata-json '{"identifier": "value", ...}'`, a single JSON object — handy
  for an agent that already holds a dictionary. Values must be strings; a
  non-string value is a usage error (exit `2`).

Supplying the same key through both is a usage error (exit `2`) raised before any
upload. A free-text annotation companion to an attribute is an ordinary key of
the form `<identifier>__annotation`, passed through unchanged.

**Output** — human: a confirmation line with the sample identifier on stdout.
`--json`: `{"id": "<sample_id>"}` on stdout.

**Exit codes** — `0` success; `2` conflicting metadata keys; `5` server
rejection (e.g. an unknown sample type or missing required metadata); `3`
authentication failure; otherwise the standard mapping above.

**Example**

```bash
$ flowbio samples upload --name liver_r1 --sample-type rna_seq \
    --reads1 ./liver_R1.fastq.gz --reads2 ./liver_R2.fastq.gz \
    --metadata strandedness=reverse
Uploaded sample samp_abc

$ flowbio samples upload --name liver_r1 --sample-type rna_seq \
    --reads1 ./liver_R1.fastq.gz --json
{"id": "samp_abc"}
```

### `samples annotation-template`

Download the server-generated annotation sheet template for a sample type, to
fill in before `samples upload-multiplexed`.

```
flowbio samples annotation-template [--sample-type TYPE] [-o PATH | --output PATH]
```

The template is an Excel workbook (`.xlsx`) keyed by metadata-attribute display
names. It is a **different artefact from the batch sample sheet** (the CLI-built
CSV used by `upload-batch`) and the two are not interchangeable. `--sample-type`
is optional and defaults to `generic` (the base columns shared by all types); a
type-specific value adds that type's metadata columns. It is sent as-is and
validated server-side.

The body is a binary workbook, so `-o/--output PATH` is **required** — it is
never written to stdout (which carries human result lines or the single JSON
document).

**Output** — human: the workbook is written to `--output`; a confirmation (path
and sample type) goes to stderr, leaving stdout empty. `--json`:
`{"output": "<path>", "sample_type": "<type>"}` on stdout — never the spreadsheet
bytes.

**Exit codes** — `0` success; `2` no `--output`, or an unwritable output path;
`4` unknown sample type; `3` authentication failure; otherwise the standard
mapping above.

**Example**

```bash
$ flowbio samples annotation-template --sample-type rna_seq -o sheet.xlsx
Wrote rna_seq annotation template to sheet.xlsx

$ flowbio samples annotation-template --sample-type rna_seq -o sheet.xlsx --json
{"output": "sheet.xlsx", "sample_type": "rna_seq"}
```

### `samples upload-multiplexed`

Upload multiplexed reads plus a completed annotation sheet for server-side
demultiplexing — single-ended (`--reads1`) or paired-end (add `--reads2`).

```
flowbio samples upload-multiplexed --reads1 PATH --annotation PATH
    [--reads2 PATH] [--reject-warnings]
```

The annotation sheet is the filled-in workbook from `annotation-template`. By
default annotation warnings are reported but the upload proceeds;
`--reject-warnings` makes warnings reject it.

**Output** — human: a confirmation line with the data identifiers and annotation
identifier on stdout, with any warnings on stderr. `--json`:
`{"data_ids": [...], "annotation_id": "<id>", "warnings": [...]}` on stdout.

**Exit codes** — `0` success (including with reported warnings); `5` annotation
fails server validation, or warnings with `--reject-warnings`; `3` authentication
failure; otherwise the standard mapping above.

**Example**

```bash
$ flowbio samples upload-multiplexed --reads1 ./mux_R1.fastq.gz \
    --annotation ./sheet.xlsx
Uploaded multiplexed data mux_1 with annotation ann_1

$ flowbio samples upload-multiplexed --reads1 ./mux_R1.fastq.gz \
    --annotation ./sheet.xlsx --json
{"data_ids": ["mux_1"], "annotation_id": "ann_1", "warnings": []}
```

### `samples batch-template`

Emit a sample-sheet template for a sample type, to fill in and feed to
`samples upload-batch`.

```
flowbio samples batch-template --sample-type TYPE [-o PATH | --output PATH]
```

Run `flowbio samples batch-template --help` for the full option list. The sample
type decides which metadata columns are marked required; it is **not** validated
here (see exit codes below) — an unrecognised type simply yields a template with
nothing flagged required-for-that-type.

**Sample-sheet schema** — the columns, in order:

- The reserved columns `name`, `reads1`, `reads2`, `project`, `organism`
  (`name` and `reads1` are always required; `reads1`/`reads2` are reads file
  paths).
- One column per metadata attribute, keyed by its **identifier**. An attribute is
  required when it is globally required or required for the chosen sample type.
- A `<identifier>__annotation` companion column immediately after each attribute
  that permits a free-text annotation.

There is **no** `sample_type` column — the type is supplied via `--sample-type`
to both this command and `upload-batch`. This CSV is distinct from the annotation
sheet produced by `samples annotation-template`.

**Output** — human: the CSV header row on stdout (or written to `--output`), plus
a summary of required-vs-optional columns on stderr. `--json`: a per-column
descriptor list on stdout (`name`, `kind` of `reserved`/`metadata`/`annotation`,
`required`, closed-value `options` or `null`, and `description`) and **no CSV** —
so an agent can build rows directly.

**Exit codes** — `0` success; `2` missing `--sample-type`; `3` authentication
failure; otherwise the standard mapping above. The sample type is not checked
against the server here, so an unknown type still exits `0`; the type is
validated when you run `samples upload-batch`.

**Example**

```bash
$ flowbio samples batch-template --sample-type rna_seq
name,reads1,reads2,project,organism,cell_type,source,source__annotation

$ flowbio samples batch-template --sample-type rna_seq --json
[{"name": "name", "kind": "reserved", "required": true, "options": null, "description": "..."}, ...]
```
