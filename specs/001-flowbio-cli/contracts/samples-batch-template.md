# Contract: `flowbio samples batch-template`

Produce an empty CSV sample sheet (or a structured column description) for a
sample type. (FR-024…FR-026)

## Synopsis

```
flowbio samples batch-template --sample-type TYPE [-o PATH | --output PATH] [global options]
```

## Arguments & options

| Name | Required | Notes |
|------|----------|-------|
| `--sample-type TYPE` | yes | Missing → exit `2`. Determines which metadata are required. |
| `-o`, `--output PATH` | no | Write the template to a file instead of stdout. |

## Behaviour

Columns, in order: reserved (`name`, `reads1`, `reads2`, `project`, `organism`),
then one column per metadata attribute, each followed by a
`<identifier>__annotation` column when the attribute allows annotation. There is
**no** `sample_type` column.

Data sourced from `client.samples.get_metadata_attributes()` (and its
`allow_annotation`, `options`, `required`, `required_for_sample_types`).

The `--sample-type` is validated against `client.samples.get_types()` before any
template is produced; an unrecognised type is a usage error listing the available
identifiers.

## Output

- **Human (no `--json`)**: CSV header row on stdout (or to `--output`); a
  human-readable summary of which columns are required vs optional for the chosen
  type on **stderr**.
- **`--json`**: a per-column descriptor list on stdout; **no CSV**:

```json
[
  {"name": "name", "kind": "reserved", "required": true, "options": null, "description": "..."},
  {"name": "<id>", "kind": "metadata", "required": false, "options": ["a","b"], "description": "..."},
  {"name": "<id>__annotation", "kind": "annotation", "required": false, "options": null, "description": "..."}
]
```

## Exit codes

`0` success; `2` missing `--sample-type`, or an unknown sample type (validated
against `get_types()`, the error lists the available identifiers); standard
mapping otherwise.

## Acceptance mapping

Spec User Story 3 scenarios 1–6.
