# Contract: `flowbio data upload`

Upload a generic data file. Wraps `client.data.upload_data(...)`. (FR-014, FR-015)

## Synopsis

```
flowbio data upload PATH [--filename NAME] [--data-type TYPE] [--directory] [global options]
```

## Arguments & options

| Name | Required | Maps to | Notes |
|------|----------|---------|-------|
| `PATH` (positional) | yes | `path` | Local file to upload. |
| `--filename NAME` | no | `filename` | Override the stored name. |
| `--data-type TYPE` | no | `data_type` | Optional; omitted → no data type sent (server defaults/infers). Not pre-validated. |
| `--directory` | no | `is_directory=True` | Upload as a directory archive. |

## Output

- **Human**: a confirmation line with the returned data identifier on stdout.
- **`--json`**: `{"id": "<data_id>"}` on stdout.

## Exit codes

`0` success; `5` server rejection (e.g. bad data type, filename with spaces);
`3` auth failure; standard mapping otherwise.

## Acceptance mapping

Spec User Story 1 scenarios 1–6.
