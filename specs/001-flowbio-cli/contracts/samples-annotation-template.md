# Contract: `flowbio samples annotation-template`

Download the server-generated annotation sheet template for a sample type, for
filling in before an `upload-multiplexed`. Wraps the existing
`client.samples.get_annotation_template(sample_type) -> bytes`. (FR-043, FR-044)

## Synopsis

```
flowbio samples annotation-template [--sample-type TYPE] [-o PATH | --output PATH] [global options]
```

## Arguments & options

| Name | Required | Maps to | Notes |
|------|----------|---------|-------|
| `--sample-type TYPE` | no | `get_annotation_template(sample_type=TYPE)` | Defaults to `"generic"` (base columns common to all types). Unlike `batch-template`, this is optional. Not pre-validated; an unknown type surfaces the server's not-found rejection. |
| `-o`, `--output PATH` | conditional | file to write | Where the workbook is written. Required when stdout is an interactive terminal (the body is binary). |

## Behaviour

- The template is a **server-generated Excel workbook** (`.xlsx`), distinct from
  the batch sample sheet: it is keyed by metadata-attribute *display names* (with
  a ` (Required)` suffix on required ones), carries a per-sample `File` column
  plus `Type`, `Sample Name`, `Project Name`, `Organism`, and `PubMed ID`, and is
  **not** interchangeable with the `batch-template` CSV. The command returns it
  verbatim — the CLI adds no shaping.
- A type-specific value (e.g. `rna_seq`) yields a template that additionally
  includes that type's metadata-attribute columns; `generic` yields only the base
  columns.

## Output

- **Human (no `--json`)**: the workbook bytes are written to `--output`; a short
  confirmation (path, sample type) goes to **stderr**. The binary is **never**
  written to a terminal stdout — without `-o` and with a TTY stdout, the command
  fails with exit `2` asking for an output path.
- **`--json`**: a single document on stdout reporting where the file was written;
  **no spreadsheet bytes** on stdout:

```json
{"output": "sheet.xlsx", "sample_type": "rna_seq"}
```

## Exit codes

`0` success; `2` no `--output` given while stdout is an interactive terminal;
`4` unknown sample type (surfaced by the server); standard mapping otherwise.

## Acceptance mapping

Spec User Story 5 scenarios 1–3.
