# Contract: `flowbio samples upload-multiplexed`

Upload multiplexed reads plus an annotation sheet for server-side demultiplexing.
Wraps `client.samples.upload_multiplexed_data(...)`. (FR-033, FR-034)

## Synopsis

```
flowbio samples upload-multiplexed --reads1 PATH --annotation PATH
    [--reads2 PATH] [--reject-warnings] [global options]
```

## Arguments & options

| Name | Required | Maps to | Notes |
|------|----------|---------|-------|
| `--reads1 PATH` | yes | `reads["reads1"]` | First reads file. |
| `--reads2 PATH` | no | `reads["reads2"]` | Paired-end. |
| `--annotation PATH` | yes | `annotation` | Annotation sheet (server-validated). |
| `--reject-warnings` | no | `ignore_warnings=False` | Warnings reject the upload. |

## Behaviour

- Default: annotation warnings are reported but the upload proceeds
  (`ignore_warnings=True`). `--reject-warnings` makes warnings reject it.
- Reports resulting data identifiers, the annotation identifier, and any
  warnings.

## Output

- **Human**: data identifiers, annotation identifier, and warnings on stdout/stderr.
- **`--json`**:

```json
{"data_ids": ["d1","d2"], "annotation_id": "ann_1", "warnings": [ ... ]}
```

## Exit codes

`0` success (incl. with reported warnings); `5` annotation fails server
validation, or warnings with `--reject-warnings`; standard mapping otherwise.

## Acceptance mapping

Spec User Story 5 scenarios 1–4.
