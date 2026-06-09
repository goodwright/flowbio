# Quickstart & Validation: flowbio CLI

Runnable scenarios that prove the feature works end-to-end. Each maps to a user
story in [spec.md](./spec.md); option/output details live in
[contracts/](./contracts/).

## Prerequisites

- A Flow API token for a test backend, or username/password.
- Local files to upload (a generic file; one or two `.fastq.gz` reads files; an
  annotation sheet for the multiplexed scenario).
- The package installed in editable mode (`pip install -e .`) **or** invoked on
  demand via `uvx` (see "Distribution" below).

## Authentication setup (any one)

```bash
export FLOW_API_TOKEN="your.jwt.token"        # direct token
# or
export FLOW_TOKEN_FILE="/path/to/api-token"   # token file
# or rely on the default file:
mkdir -p ~/.config/flow && printf '%s' "your.jwt.token" > ~/.config/flow/api-token
# or omit all of the above to be prompted for username/password (TTY only)
```

Optional: `export FLOW_API_URL="https://app.flow.bio/api"`.

## Scenario 1 — Upload a generic data file (User Story 1)

```bash
flowbio data upload ./counts.tsv
# → confirmation line with the data identifier, exit 0

flowbio data upload ./counts.tsv --json
# → {"id": "..."} on stdout only, exit 0
```

**Expect**: machine-readable single document under `--json`; a server rejection
(e.g. `--data-type bogus`) exits `5`; an invalid token exits `3`.

## Scenario 2 — Upload a single sample (User Story 2)

```bash
flowbio samples upload --name s1 --sample-type rna_seq --reads1 r1.fq.gz
flowbio samples upload --name s1 --sample-type rna_seq --reads1 r1.fq.gz --reads2 r2.fq.gz
flowbio samples upload --name s1 --sample-type rna_seq --reads1 r1.fq.gz \
    --metadata strandedness=reverse --metadata source=blood
flowbio samples upload --name s1 --sample-type rna_seq --reads1 r1.fq.gz \
    --metadata-json '{"strandedness": "reverse"}'
```

**Expect**: sample identifier printed; supplying the same key via both
`--metadata` and `--metadata-json` exits `2` before uploading.

## Scenario 3 — Generate a sample-sheet template (User Story 3)

```bash
flowbio samples batch-template --sample-type rna_seq
# → CSV header (reserved + metadata columns, no sample_type) on stdout;
#   required/optional summary on stderr

flowbio samples batch-template --sample-type rna_seq -o sheet.csv
flowbio samples batch-template --sample-type rna_seq --json
# → per-column descriptor list on stdout, no CSV
```

**Expect**: an annotation-enabled attribute yields a `<id>__annotation` column;
omitting `--sample-type` exits `2`.

## Scenario 4 — Upload a batch from a sample sheet (User Story 4)

Author `sheet.csv` (paths relative to the sheet's directory):

```csv
name,reads1,reads2,project,organism,strandedness
s1,r1.fq.gz,r2.fq.gz,,,reverse
s2,s2_r1.fq.gz,,,,forward
```

```bash
flowbio samples upload-batch --sheet sheet.csv --sample-type rna_seq
flowbio samples upload-batch --sheet sheet.csv --sample-type rna_seq --json
flowbio samples upload-batch --sheet sheet.csv --sample-type rna_seq --skip-invalid
flowbio samples upload-batch --sheet sheet.csv --sample-type rna_seq --stop-on-error
```

**Expect**: all rows validated before any upload; an invalid sheet reports every
row's error and uploads nothing (exit `2`); `--json` returns
`uploaded`/`failed`/`skipped` + `counts`; passing an `.xlsx`/`.tsv` exits `2`
with an "export to CSV" message; a row failing at the server exits `1`.

## Scenario 5 — Multiplexed upload with an annotation sheet (User Story 5)

First download the annotation sheet template, fill it in, then submit it with the
reads:

```bash
flowbio samples annotation-template --sample-type rna_seq -o annotation.xlsx
# → server-generated .xlsx template written to annotation.xlsx; confirmation on stderr

flowbio samples annotation-template -o generic.xlsx            # generic (no --sample-type)
flowbio samples annotation-template --sample-type rna_seq --json
# → {"output": "...", "sample_type": "rna_seq"} on stdout, no binary on stdout
```

```bash
flowbio samples upload-multiplexed --reads1 r1.fq.gz --annotation annotation.xlsx
flowbio samples upload-multiplexed --reads1 r1.fq.gz --reads2 r2.fq.gz --annotation annotation.xlsx
flowbio samples upload-multiplexed --reads1 r1.fq.gz --annotation annotation.xlsx --reject-warnings
```

**Expect**: the template downloads as a binary `.xlsx` (writing to a terminal
stdout without `-o` exits `2`; an unknown `--sample-type` exits `4`); the
annotation sheet is **not** the batch sample sheet of Scenario 3/4 and the two are
not interchangeable. On upload, data identifiers, annotation identifier, and
warnings are reported; warnings proceed by default but reject under
`--reject-warnings`; failed annotation validation exits `5`.

## Cross-cutting checks

```bash
flowbio --version            # prints version, exit 0
flowbio                       # help + exit 2
flowbio data                  # help + exit 2
flowbio --json samples upload --name s1 --sample-type rna_seq --reads1 r1.fq.gz
flowbio samples upload --name s1 --sample-type rna_seq --reads1 r1.fq.gz --json   # identical to above
```

Non-interactive guard:

```bash
env -u FLOW_API_TOKEN -u FLOW_TOKEN_FILE flowbio data upload ./counts.tsv < /dev/null
# → fails fast with exit 2 (would otherwise need a prompt), does not hang
```

## Distribution (SC-006)

```bash
uvx --from "flowbio==X.Y.Z" flowbio --version
uvx --from "flowbio==X.Y.Z" flowbio data upload ./counts.tsv --json
```

**Expect**: resolves and runs from the published package in an ephemeral
environment, without a global install or local source.

## Automated validation

```bash
pytest tests/unit/cli         # CLI unit/contract tests (respx-mocked HTTP)
pytest                         # full suite, including the additive MetadataAttribute field
```
