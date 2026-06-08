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
  for an agent that already holds a dictionary.

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
