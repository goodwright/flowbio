"""The ``flowbio samples`` command group (FR-016…FR-019).

A thin wrapper over :attr:`Client.samples <flowbio.v2.Client.samples>`: it parses
the command line, merges metadata supplied as ``key=value`` pairs and/or a JSON
object, calls the library, and renders the result. Most commands send
``--sample-type`` as-is for server-side validation; ``batch-template`` is the
exception, pre-checking the type against the available types up front.
"""
from __future__ import annotations

import argparse
import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from flowbio.cli._accession_sheet import (
    AccessionSheetRow,
    duplicate_accession_errors,
    parse_accession_sheet,
    validate_accession_row,
)
from flowbio.cli._exit_codes import CliUsageError, ExitCode
from flowbio.cli._files import existing_file
from flowbio.cli._output import Output, format_issue
from flowbio.cli._sheet import (
    ANNOTATION_SUFFIX,
    SheetRow,
    parse_sheet,
    validate_row,
)
from flowbio.cli._types import JsonValue
from flowbio.v2.client import Client
from flowbio.v2.exceptions import FlowApiError
from flowbio.v2.samples import (
    MetadataAttribute,
    SampleImportJob,
    SampleImportJobId,
    SampleImportSpec,
    SampleImportStatus,
    SampleTypeId,
)


def register(
    resource: argparse.ArgumentParser, global_parent: argparse.ArgumentParser,
) -> None:
    """Register the ``samples`` verbs on the resource parser."""
    verbs = resource.add_subparsers(dest="verb", metavar="<verb>")
    _configure_upload(verbs.add_parser(
        "upload",
        parents=[global_parent],
        help="Upload a single demultiplexed sample.",
        description="Upload a single demultiplexed sample to the Flow platform.",
    ))
    _configure_annotation_template(verbs.add_parser(
        "annotation-template",
        parents=[global_parent],
        help="Download the annotation sheet template for multiplexed uploads.",
        description=(
            "Download the server-generated annotation sheet (.xlsx) template for a "
            "sample type, to fill in before `samples upload-multiplexed`."
        ),
    ))
    _configure_upload_multiplexed(verbs.add_parser(
        "upload-multiplexed",
        parents=[global_parent],
        help="Upload multiplexed reads with an annotation sheet.",
        description=(
            "Upload multiplexed reads plus a completed annotation sheet for "
            "server-side demultiplexing."
        ),
    ))
    _configure_batch_template(verbs.add_parser(
        "batch-template",
        parents=[global_parent],
        help="Emit a sample-sheet template for a sample type.",
        description=(
            "Emit a CSV sample-sheet header (or a per-column descriptor under "
            "--json) for use with 'samples upload-batch'."
        ),
    ))
    _configure_upload_batch(verbs.add_parser(
        "upload-batch",
        parents=[global_parent],
        help="Upload many samples from a CSV sample sheet.",
        description=(
            "Validate every row of a CSV sample sheet up front, then upload the "
            "valid rows sequentially, reporting each row's outcome."
        ),
    ))
    _configure_import(verbs.add_parser(
        "import",
        parents=[global_parent],
        help="Import samples from public-repository accessions.",
        description=(
            "Validate every row of a CSV accession sheet up front, kick off a "
            "single import job for the valid rows, poll it to completion, and "
            "report each accession's outcome."
        ),
    ))


def _configure_upload(upload: argparse.ArgumentParser) -> None:
    upload.set_defaults(command_parser=upload, handler=_upload_command)
    upload.add_argument(
        "--name",
        required=True,
        metavar="NAME",
        help="Sample name (spaces are rejected server-side).",
    )
    upload.add_argument(
        "--sample-type",
        required=True,
        metavar="TYPE",
        type=SampleTypeId,
        help="Sample type identifier (sent as-is; validated server-side).",
    )
    upload.add_argument(
        "--reads1",
        required=True,
        metavar="PATH",
        type=Path,
        help="First reads file.",
    )
    upload.add_argument(
        "--reads2",
        metavar="PATH",
        type=Path,
        help="Second reads file (makes the sample paired-end).",
    )
    upload.add_argument(
        "--project",
        metavar="ID",
        help="Project to assign the sample to.",
    )
    upload.add_argument(
        "--organism",
        metavar="ID",
        help="Organism to associate with the sample.",
    )
    upload.add_argument(
        "--metadata",
        action="append",
        metavar="KEY=VALUE",
        help="Metadata attribute, repeatable; split on the first '='.",
    )
    upload.add_argument(
        "--metadata-json",
        metavar="JSON",
        help="Metadata as a JSON object of identifier to value.",
    )


def _configure_annotation_template(annotation_template: argparse.ArgumentParser) -> None:
    annotation_template.set_defaults(
        command_parser=annotation_template, handler=_annotation_template_command,
    )
    annotation_template.add_argument(
        "--sample-type",
        default="generic",
        metavar="TYPE",
        type=SampleTypeId,
        help=(
            "Sample type identifier (sent as-is; validated server-side). "
            "Defaults to 'generic' (base columns common to all types)."
        ),
    )
    annotation_template.add_argument(
        "-o",
        "--output",
        required=True,
        metavar="PATH",
        type=Path,
        help="File to write the .xlsx workbook to (the template is binary).",
    )


def _configure_upload_multiplexed(upload_multiplexed: argparse.ArgumentParser) -> None:
    upload_multiplexed.set_defaults(
        command_parser=upload_multiplexed, handler=_upload_multiplexed_command,
    )
    upload_multiplexed.add_argument(
        "--reads1",
        required=True,
        metavar="PATH",
        type=Path,
        help="First multiplexed reads file.",
    )
    upload_multiplexed.add_argument(
        "--reads2",
        metavar="PATH",
        type=Path,
        help="Second multiplexed reads file (makes the upload paired-end).",
    )
    upload_multiplexed.add_argument(
        "--annotation",
        required=True,
        metavar="PATH",
        type=Path,
        help="Completed annotation sheet (obtained via `annotation-template`).",
    )
    upload_multiplexed.add_argument(
        "--reject-warnings",
        action="store_true",
        help="Reject the upload if the annotation sheet has warnings.",
    )


def _configure_batch_template(batch_template: argparse.ArgumentParser) -> None:
    batch_template.set_defaults(
        command_parser=batch_template, handler=_batch_template_command,
    )
    batch_template.add_argument(
        "--sample-type",
        required=True,
        metavar="TYPE",
        type=SampleTypeId,
        help="Sample type the template is built for (decides required columns).",
    )
    batch_template.add_argument(
        "-o", "--output",
        metavar="PATH",
        type=Path,
        help="Write the CSV template to this file instead of stdout.",
    )


def _configure_upload_batch(upload_batch: argparse.ArgumentParser) -> None:
    upload_batch.set_defaults(
        command_parser=upload_batch, handler=_upload_batch_command,
    )
    upload_batch.add_argument(
        "--sheet",
        required=True,
        metavar="PATH",
        type=Path,
        help="CSV sample sheet (the filled-in `samples batch-template` output).",
    )
    upload_batch.add_argument(
        "--sample-type",
        required=True,
        metavar="TYPE",
        type=SampleTypeId,
        help="Sample type applied to every row (sent as-is; validated server-side).",
    )
    upload_batch.add_argument(
        "--skip-invalid",
        action="store_true",
        help="Skip invalid rows (reporting why) instead of aborting the batch.",
    )
    upload_batch.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Abort on the first row that fails to upload.",
    )


_DEFAULT_POLL_INTERVAL = 5.0
_DEFAULT_TIMEOUT = 1800.0


def _positive_float(value: str) -> float:
    parsed = float(value)
    if not math.isfinite(parsed) or parsed <= 0:
        raise argparse.ArgumentTypeError(f"must be a positive, finite number, got {value!r}")
    return parsed


def _configure_import(import_parser: argparse.ArgumentParser) -> None:
    import_parser.set_defaults(command_parser=import_parser, handler=_import_command)
    import_parser.add_argument(
        "--sheet",
        required=True,
        metavar="PATH",
        type=Path,
        help="CSV accession sheet (accession, optional name/organism, plus metadata columns).",
    )
    import_parser.add_argument(
        "--sample-type",
        required=True,
        metavar="TYPE",
        type=SampleTypeId,
        help="Sample type applied to every accession (sent as-is; validated server-side).",
    )
    import_parser.add_argument(
        "--skip-invalid",
        action="store_true",
        help="Skip invalid rows (reporting why) instead of aborting the import.",
    )
    import_parser.add_argument(
        "--poll-interval",
        type=_positive_float,
        default=_DEFAULT_POLL_INTERVAL,
        metavar="SECONDS",
        help=(
            "Seconds to wait between checks of the import job's status; must be "
            f"positive (default: {_DEFAULT_POLL_INTERVAL:g})."
        ),
    )
    import_parser.add_argument(
        "--timeout",
        type=_positive_float,
        default=_DEFAULT_TIMEOUT,
        metavar="SECONDS",
        help=(
            "Maximum seconds to wait for the import job to finish; must be "
            f"positive (default: {_DEFAULT_TIMEOUT:g})."
        ),
    )


def _upload_command(args: argparse.Namespace, client: Client, output: Output) -> ExitCode:
    """Upload a single sample and report its identifier.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` on success.
    """
    metadata = _merge_metadata(args.metadata, args.metadata_json)
    data = {"reads1": existing_file(args.reads1)}
    if args.reads2 is not None:
        data["reads2"] = existing_file(args.reads2)
    sample = client.samples.upload_sample(
        name=args.name,
        sample_type=args.sample_type,
        data=data,
        metadata=metadata or None,
        project_id=args.project,
        organism_id=args.organism,
    )
    output.emit_result(f"Uploaded sample {sample.id}", {"id": sample.id})
    return ExitCode.SUCCESS


def _annotation_template_command(
    args: argparse.Namespace, client: Client, output: Output,
) -> ExitCode:
    """Download an annotation sheet template and write it to a file.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` on success.
    """
    destination = args.output
    template = client.samples.get_annotation_template(args.sample_type)
    try:
        destination.write_bytes(template)
    except OSError as error:
        raise CliUsageError(
            f"Could not write annotation template to {destination}: {error}",
        ) from error
    if output.json_mode:
        output.emit_result(
            "", {"output": str(destination), "sample_type": args.sample_type},
        )
    else:
        output.emit_advisory(
            f"Wrote {args.sample_type} annotation template to {destination}",
        )
    return ExitCode.SUCCESS


def _upload_multiplexed_command(
    args: argparse.Namespace, client: Client, output: Output,
) -> ExitCode:
    """Upload multiplexed reads and an annotation sheet, reporting identifiers.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` on success.
    """
    reads = {"reads1": existing_file(args.reads1)}
    if args.reads2 is not None:
        reads["reads2"] = existing_file(args.reads2)
    upload = client.samples.upload_multiplexed_data(
        reads=reads,
        annotation=existing_file(args.annotation),
        ignore_warnings=not args.reject_warnings,
    )
    if upload.warnings:
        output.emit_advisory("Annotation warnings:")
        for warning in upload.warnings:
            output.emit_advisory(f"  {format_issue(warning)}")
    output.emit_result(
        f"Uploaded multiplexed data {', '.join(upload.data_ids)} "
        f"with annotation {upload.annotation_id}",
        {
            "data_ids": upload.data_ids,
            "annotation_id": upload.annotation_id,
            "warnings": upload.warnings,
        },
    )
    return ExitCode.SUCCESS


@dataclass(frozen=True)
class _TemplateColumn:
    """One column of a sample-sheet template, in CSV order."""

    name: str
    kind: Literal["reserved", "metadata", "annotation"]
    required: bool
    options: list[str] | None
    description: str

    @property
    def descriptor(self) -> dict[str, JsonValue]:
        return {
            "name": self.name,
            "kind": self.kind,
            "required": self.required,
            "options": self.options,
            "description": self.description,
        }


_RESERVED_COLUMNS = (
    _TemplateColumn("name", "reserved", True, None, "Unique sample name (no spaces)."),
    _TemplateColumn("reads1", "reserved", True, None, "Path to the first reads file."),
    _TemplateColumn("reads2", "reserved", False, None, "Path to the second reads file (paired-end)."),
    _TemplateColumn("project", "reserved", False, None, "Project identifier to assign the sample to."),
    _TemplateColumn("organism", "reserved", False, None, "Organism identifier to associate with the sample."),
)


def _batch_template_command(
    args: argparse.Namespace, client: Client, output: Output,
) -> ExitCode:
    """Emit a sample-sheet template for the chosen sample type.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` on success.
    """
    _check_sample_type(client, args.sample_type)
    columns = _template_columns(
        client.samples.get_metadata_attributes(), args.sample_type,
    )
    header = ",".join(column.name for column in columns)
    if args.output is not None:
        try:
            args.output.write_text(f"{header}\n")
        except OSError as error:
            raise CliUsageError(
                f"Could not write sample-sheet template to {args.output}: {error}",
            ) from error
        output.emit_advisory(f"Wrote sample-sheet template to {args.output}")
    if output.json_mode or args.output is None:
        output.emit_result(header, [column.descriptor for column in columns])
    output.emit_advisory(_required_summary(columns))
    return ExitCode.SUCCESS


def _check_sample_type(client: Client, sample_type: SampleTypeId) -> None:
    identifiers = [sample.identifier for sample in client.samples.get_types()]
    if sample_type not in identifiers:
        raise CliUsageError(
            f"Unknown sample type '{sample_type}'. "
            f"Available types: {', '.join(sorted(identifiers))}",
        )


def _template_columns(
    attributes: list[MetadataAttribute], sample_type: SampleTypeId,
) -> list[_TemplateColumn]:
    columns = list(_RESERVED_COLUMNS)
    for attribute in attributes:
        required = (
            attribute.required or sample_type in attribute.required_for_sample_types
        )
        columns.append(
            _TemplateColumn(
                name=attribute.identifier,
                kind="metadata",
                required=required,
                options=attribute.options,
                description=attribute.description,
            ),
        )
        if attribute.allow_annotation:
            columns.append(
                _TemplateColumn(
                    name=f"{attribute.identifier}{ANNOTATION_SUFFIX}",
                    kind="annotation",
                    required=False,
                    options=None,
                    description=f"Free-text annotation for {attribute.identifier}.",
                ),
            )
    return columns


def _required_summary(columns: list[_TemplateColumn]) -> str:
    required = [column.name for column in columns if column.required]
    optional = [column.name for column in columns if not column.required]
    return (
        f"Required columns: {', '.join(required)}\n"
        f"Optional columns: {', '.join(optional)}"
    )


@dataclass(frozen=True)
class _BatchResult:
    """The outcome of an ``upload-batch`` run, rendered to text or JSON."""

    uploaded: list[dict[str, JsonValue]]
    failed: list[dict[str, JsonValue]]
    skipped: list[dict[str, JsonValue]]

    @property
    def counts(self) -> dict[str, int]:
        return {
            "uploaded": len(self.uploaded),
            "failed": len(self.failed),
            "skipped": len(self.skipped),
        }

    @property
    def document(self) -> dict[str, JsonValue]:
        return {
            "uploaded": self.uploaded,
            "failed": self.failed,
            "skipped": self.skipped,
            "counts": self.counts,
        }

    @property
    def summary(self) -> str:
        counts = self.counts
        return (
            f"Uploaded {counts['uploaded']}, failed {counts['failed']}, "
            f"skipped {counts['skipped']}."
        )

    @property
    def exit_code(self) -> ExitCode:
        return ExitCode.RUNTIME if self.failed else ExitCode.SUCCESS


def _upload_batch_command(
    args: argparse.Namespace, client: Client, output: Output,
) -> ExitCode:
    """Validate a sample sheet up front, then upload the valid rows.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` when every row uploaded,
        :attr:`ExitCode.USAGE` on a pre-flight validation failure without
        ``--skip-invalid``, or :attr:`ExitCode.RUNTIME` if any upload failed.
    """
    sheet = parse_sheet(args.sheet)
    attributes = client.samples.get_metadata_attributes()
    classified = [
        (row, validate_row(row, attributes, args.sample_type))
        for row in sheet.rows
    ]
    invalid = [(row, reasons) for row, reasons in classified if reasons]
    valid = [row for row, reasons in classified if not reasons]

    if invalid and not args.skip_invalid:
        output.emit_error(
            "Sample sheet has invalid rows; nothing was uploaded.",
            details=[_invalid_line(row, reasons) for row, reasons in invalid],
        )
        return ExitCode.USAGE

    for row, reasons in invalid:
        output.emit_advisory(f"Skipped {_invalid_line(row, reasons)}")
    skipped = [
        {"row_number": row.row_number, "name": row.name, "reasons": reasons}
        for row, reasons in invalid
    ]
    result = _upload_rows(valid, args, client, output, skipped)
    output.emit_result(result.summary, result.document)
    return result.exit_code


def _upload_rows(
    rows: list[SheetRow],
    args: argparse.Namespace,
    client: Client,
    output: Output,
    skipped: list[dict[str, JsonValue]],
) -> _BatchResult:
    uploaded: list[dict[str, JsonValue]] = []
    failed: list[dict[str, JsonValue]] = []
    for row in rows:
        try:
            sample = client.samples.upload_sample(
                name=row.name,
                sample_type=args.sample_type,
                data=_row_reads(row),
                metadata=row.metadata or None,
                project_id=row.project,
                organism_id=row.organism,
            )
        except FlowApiError as error:
            failed.append({
                "row_number": row.row_number,
                "name": row.name,
                "message": error.message,
            })
            output.emit_advisory(
                f"Row {row.row_number} ({row.name}): upload failed — {error.message}",
            )
            if args.stop_on_error:
                break
            continue
        uploaded.append({
            "row_number": row.row_number,
            "name": row.name,
            "sample_id": sample.id,
        })
        output.emit_advisory(
            f"Row {row.row_number} ({row.name}): uploaded {sample.id}",
        )
    return _BatchResult(uploaded=uploaded, failed=failed, skipped=skipped)


def _row_reads(row: SheetRow) -> dict[str, Path]:
    return {
        label: path
        for label, path in (("reads1", row.reads1), ("reads2", row.reads2))
        if path is not None
    }


def _invalid_line(row: SheetRow, reasons: list[str]) -> str:
    return f"Row {row.row_number} ({row.name}): {'; '.join(reasons)}"


@dataclass(frozen=True)
class _ImportResult:
    """The outcome of an ``import`` run, rendered to text or JSON.

    Unlike :class:`_BatchResult`, every accession shares one server-side job:
    all rows land in ``imported`` together on a completed job, or all land in
    ``failed`` together (carrying the job's one error message) otherwise. Each
    ``failed`` entry carries a ``status`` of ``"failed"`` (the job genuinely
    failed, or completed without creating that row's sample), ``"running"``
    (the job timed out but may still complete), or ``"unknown"`` (the job's
    accessions/sample_ids couldn't be matched to rows) — only ``"failed"`` is
    safe to blindly retry. ``job_sample_ids`` carries whatever sample ids the
    job did return, verbatim and unattributed to any row, so a ``"running"``
    or ``"unknown"`` outcome doesn't hide that the job may already have
    created something. ``job_id``/``job_status``/``execution_id`` are
    ``None`` only when no job was ever created (every row was invalid or
    skipped), so a timed-out or interrupted run can still be resumed with
    :meth:`~flowbio.v2.samples.SampleResource.get_import`.
    """

    imported: list[dict[str, JsonValue]]
    failed: list[dict[str, JsonValue]]
    skipped: list[dict[str, JsonValue]]
    job_id: SampleImportJobId | None = None
    job_status: SampleImportStatus | None = None
    execution_id: int | None = None
    job_sample_ids: list[int] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        return {
            "imported": len(self.imported),
            "failed": len(self.failed),
            "skipped": len(self.skipped),
        }

    @property
    def document(self) -> dict[str, JsonValue]:
        return {
            "imported": self.imported,
            "failed": self.failed,
            "skipped": self.skipped,
            "counts": self.counts,
            "job_id": self.job_id,
            "job_status": self.job_status,
            "execution_id": self.execution_id,
            "job_sample_ids": self.job_sample_ids,
        }

    @property
    def summary(self) -> str:
        counts = self.counts
        return (
            f"Imported {counts['imported']}, failed {counts['failed']}, "
            f"skipped {counts['skipped']}."
        )

    @property
    def exit_code(self) -> ExitCode:
        return ExitCode.RUNTIME if self.failed else ExitCode.SUCCESS


def _import_command(
    args: argparse.Namespace, client: Client, output: Output,
) -> ExitCode:
    """Validate an accession sheet up front, then run one import job for it.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` when the import job completes,
        :attr:`ExitCode.USAGE` on a pre-flight validation failure without
        ``--skip-invalid``, or :attr:`ExitCode.RUNTIME` if the import job
        fails or does not finish within ``--timeout``.
    """
    sheet = parse_accession_sheet(args.sheet)
    attributes = client.samples.get_metadata_attributes()
    duplicates = duplicate_accession_errors(sheet.rows)
    classified = [
        (
            row,
            validate_accession_row(row, attributes, args.sample_type)
            + duplicates.get(row.row_number, []),
        )
        for row in sheet.rows
    ]
    invalid = [(row, reasons) for row, reasons in classified if reasons]
    valid = [row for row, reasons in classified if not reasons]

    if invalid and not args.skip_invalid:
        output.emit_error(
            "Accession sheet has invalid rows; nothing was imported.",
            details=[_invalid_accession_line(row, reasons) for row, reasons in invalid],
        )
        return ExitCode.USAGE

    for row, reasons in invalid:
        output.emit_advisory(f"Skipped {_invalid_accession_line(row, reasons)}")
    skipped = [
        {"row_number": row.row_number, "accession": row.accession, "reasons": reasons}
        for row, reasons in invalid
    ]

    result = _run_import(valid, args, client, output, skipped)
    output.emit_result(result.summary, result.document)
    return result.exit_code


def _run_import(
    rows: list[AccessionSheetRow],
    args: argparse.Namespace,
    client: Client,
    output: Output,
    skipped: list[dict[str, JsonValue]],
) -> _ImportResult:
    if not rows:
        return _ImportResult(imported=[], failed=[], skipped=skipped)

    specs = [
        SampleImportSpec(
            accession=row.accession,
            sample_type=args.sample_type,
            name=row.name,
            organism_id=row.organism,
            metadata=row.metadata or None,
        )
        for row in rows
    ]
    job = client.samples.import_samples(specs)
    output.emit_advisory(f"Import job {job.id} started for {len(rows)} accession(s); polling...")
    job = _poll_job(client, job, args.poll_interval, args.timeout)
    return _import_result(job, rows, skipped, output)


def _poll_job(
    client: Client, job: SampleImportJob, poll_interval: float, timeout: float,
) -> SampleImportJob:
    deadline = time.monotonic() + timeout
    while job.status == "RUNNING":
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))
        job = client.samples.get_import(job.id)
    return job


def _import_result(
    job: SampleImportJob,
    rows: list[AccessionSheetRow],
    skipped: list[dict[str, JsonValue]],
    output: Output,
) -> _ImportResult:
    if _sample_ids_unmatchable(job):
        imported: list[dict[str, JsonValue]] = []
        failed = _mismatched_outcome(job, rows, output)
    else:
        accession_to_sample_id = dict(zip(job.accessions, job.sample_ids))
        if job.status == "COMPLETED":
            imported, failed = _completed_outcomes(job, rows, accession_to_sample_id, output)
        else:
            imported, failed = [], _failed_outcomes(job, rows, accession_to_sample_id, output)
    return _ImportResult(
        imported=imported,
        failed=failed,
        skipped=skipped,
        job_id=job.id,
        job_status=job.status,
        execution_id=job.execution_id,
        job_sample_ids=list(job.sample_ids),
    )


def _sample_ids_unmatchable(job: SampleImportJob) -> bool:
    # An empty sample_ids is the normal, expected shape before anything has
    # been created (RUNNING) or when nothing survived to be created (FAILED).
    # A COMPLETED job is different: it has told us the batch is done, so
    # returning zero sample ids for one or more accessions is exactly as
    # broken an invariant as any other length mismatch, not a quiet success.
    if not job.sample_ids:
        return job.status == "COMPLETED"
    return len(job.sample_ids) != len(job.accessions)


def _mismatched_outcome(
    job: SampleImportJob, rows: list[AccessionSheetRow], output: Output,
) -> list[dict[str, JsonValue]]:
    message = (
        f"import job {job.id} returned {len(job.sample_ids)} sample id(s) for "
        f"{len(job.accessions)} accession(s); cannot match them to rows"
    )
    failed: list[dict[str, JsonValue]] = []
    for row in rows:
        failed.append({
            "row_number": row.row_number,
            "accession": row.accession,
            "message": message,
            "status": "unknown",
        })
        output.emit_advisory(f"Row {row.row_number} ({row.accession}): import outcome unknown — {message}")
    return failed


def _completed_outcomes(
    job: SampleImportJob,
    rows: list[AccessionSheetRow],
    accession_to_sample_id: dict[str, int],
    output: Output,
) -> tuple[list[dict[str, JsonValue]], list[dict[str, JsonValue]]]:
    imported: list[dict[str, JsonValue]] = []
    failed: list[dict[str, JsonValue]] = []
    for row in rows:
        sample_id = accession_to_sample_id.get(row.accession)
        if sample_id is None:
            message = f"import job {job.id} completed but returned no sample id for this accession"
            failed.append({
                "row_number": row.row_number, "accession": row.accession,
                "message": message, "status": "failed",
            })
            output.emit_advisory(f"Row {row.row_number} ({row.accession}): import failed — {message}")
            continue
        imported.append({"row_number": row.row_number, "accession": row.accession, "sample_id": sample_id})
        output.emit_advisory(f"Row {row.row_number} ({row.accession}): imported sample {sample_id}")
    return imported, failed


def _failed_outcomes(
    job: SampleImportJob,
    rows: list[AccessionSheetRow],
    accession_to_sample_id: dict[str, int],
    output: Output,
) -> list[dict[str, JsonValue]]:
    timed_out = job.status == "RUNNING"
    if timed_out:
        message = (
            f"import job {job.id} did not finish within the configured timeout "
            f"(still RUNNING) — check it later with client.samples.get_import({job.id})"
        )
        verb = "did not finish"
    else:
        message = job.error or f"import job {job.id} ended with status {job.status}"
        verb = "failed"
    entry_status = "running" if timed_out else "failed"
    failed: list[dict[str, JsonValue]] = []
    for row in rows:
        entry: dict[str, JsonValue] = {
            "row_number": row.row_number, "accession": row.accession,
            "message": message, "status": entry_status,
        }
        sample_id = accession_to_sample_id.get(row.accession)
        advisory = f"Row {row.row_number} ({row.accession}): import {verb} — {message}"
        if sample_id is not None:
            entry["sample_id"] = sample_id
            advisory += f" (sample {sample_id} was created)"
        failed.append(entry)
        output.emit_advisory(advisory)
    return failed


def _invalid_accession_line(row: AccessionSheetRow, reasons: list[str]) -> str:
    return f"Row {row.row_number} ({row.accession or '<blank>'}): {'; '.join(reasons)}"


def _merge_metadata(
    pairs: list[str] | None, json_text: str | None,
) -> dict[str, str]:
    from_pairs = _parse_pairs(pairs)
    from_json = _parse_json(json_text)
    conflicts = sorted(from_pairs.keys() & from_json.keys())
    if conflicts:
        raise CliUsageError(
            f"Metadata key(s) supplied by both --metadata and --metadata-json: "
            f"{', '.join(conflicts)}",
        )
    return {**from_pairs, **from_json}


def _parse_pairs(pairs: list[str] | None) -> dict[str, str]:
    result: dict[str, str] = {}
    for pair in pairs or []:
        key, separator, value = pair.partition("=")
        if not separator or not key:
            raise CliUsageError(f"Invalid --metadata '{pair}': expected KEY=VALUE.")
        result[key] = value
    return result


def _parse_json(json_text: str | None) -> dict[str, str]:
    if json_text is None:
        return {}
    try:
        parsed = json.loads(json_text)
    except json.JSONDecodeError as error:
        raise CliUsageError(f"--metadata-json is not valid JSON: {error}") from error
    if not isinstance(parsed, dict):
        raise CliUsageError("--metadata-json must be a JSON object.")
    non_string = sorted(key for key, value in parsed.items() if not isinstance(value, str))
    if non_string:
        raise CliUsageError(
            f"--metadata-json values must be strings; non-string value(s) for: "
            f"{', '.join(non_string)}",
        )
    return dict(parsed)
