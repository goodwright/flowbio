# Contract: `flowbio samples upload-batch`

Upload many samples from a CSV sample sheet, one sample type applied to all rows.
(FR-020…FR-023, FR-027…FR-032)

## Synopsis

```
flowbio samples upload-batch --sheet PATH --sample-type TYPE
    [--skip-invalid] [--stop-on-error] [global options]
```

## Arguments & options

| Name | Required | Notes |
|------|----------|-------|
| `--sheet PATH` | yes | CSV sample sheet. Non-CSV (`.xlsx`, `.tsv`) → exit `2`, "export to CSV". |
| `--sample-type TYPE` | yes | Applied uniformly to every row; sent as-is. |
| `--skip-invalid` | no | Skip invalid rows (report reasons) instead of aborting. |
| `--stop-on-error` | no | Abort on the first failing upload (earliest row order). |

## Sheet schema

Reserved columns: `name` (req), `reads1` (req), `reads2`, `project`, `organism`.
Every other header = a metadata identifier (incl. `<id>__annotation`). Empty
cells omitted. Reads paths resolve relative to the **sheet file's directory**;
absolute paths used as-is.

## Behaviour

1. Parse the entire sheet; validate **every** row before any upload (FR-027/028):
   required reserved values; required metadata for the type; reads files exist;
   name has no spaces; closed-option values within `options`; annotation set only
   with its value and only for annotation-enabled attributes.
2. Any invalid row, default → report **all** per-row errors (1-based row number +
   name), upload nothing, exit `2`. With `--skip-invalid` → skip & report those,
   upload the rest.
3. Upload valid rows **sequentially in sheet order**. Default → continue past
   per-row upload failures (record each); `--stop-on-error` → abort on first
   failure, reporting already-uploaded rows.
4. Nothing fails silently — every error carries row number, name, and message.

## Output

- **Human**: per-row outcomes on stderr; final counts summary.
- **`--json`** (FR-032):

```json
{
  "uploaded": [{"row_number": 1, "name": "s1", "sample_id": "samp_1"}],
  "failed":   [{"row_number": 2, "name": "s2", "message": "..."}],
  "skipped":  [{"row_number": 3, "name": "s3", "reasons": ["..."]}],
  "counts":   {"uploaded": 1, "failed": 1, "skipped": 1}
}
```

## Exit codes

`0` all uploaded; `2` pre-flight validation failure (no `--skip-invalid`) or
non-CSV sheet; `1` any upload failure; standard mapping otherwise.

## Acceptance mapping

Spec User Story 4 scenarios 1–7.
