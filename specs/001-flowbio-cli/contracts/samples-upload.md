# Contract: `flowbio samples upload`

Upload a single demultiplexed sample. Wraps `client.samples.upload_sample(...)`.
(FR-016…FR-019)

## Synopsis

```
flowbio samples upload --name NAME --sample-type TYPE --reads1 PATH
    [--reads2 PATH] [--project ID] [--organism ID]
    [--metadata key=value ...] [--metadata-json JSON] [global options]
```

## Arguments & options

| Name | Required | Maps to | Notes |
|------|----------|---------|-------|
| `--name NAME` | yes | `name` | Sample name (no spaces — server rejects). |
| `--sample-type TYPE` | yes | `sample_type` | Sent as-is; not pre-validated. |
| `--reads1 PATH` | yes | `data["reads1"]` | First reads file. |
| `--reads2 PATH` | no | `data["reads2"]` | Makes it paired-end. |
| `--project ID` | no | `project_id` | Optional project. |
| `--organism ID` | no | `organism_id` | Optional organism. |
| `--metadata key=value` | no (repeatable) | `metadata` | Split on first `=`. |
| `--metadata-json JSON` | no | `metadata` | Identifier→value object. |

## Metadata rules

- `--metadata` and `--metadata-json` are merged.
- Same key in both → exit `2` (usage error) before any upload.
- Annotation companions: ordinary keys `<identifier>__annotation`, passed
  through unchanged.

## Output

- **Human**: confirmation line with the returned sample identifier on stdout.
- **`--json`**: `{"id": "<sample_id>"}` on stdout.

## Exit codes

`0` success; `2` conflicting metadata keys; `5` server rejection (unknown sample
type, missing required metadata); standard mapping otherwise.

## Acceptance mapping

Spec User Story 2 scenarios 1–6.
