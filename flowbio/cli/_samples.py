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
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from flowbio.cli._exit_codes import CliUsageError, ExitCode
from flowbio.cli._files import existing_file
from flowbio.cli._output import Output, format_issue
from flowbio.cli._types import JsonValue
from flowbio.v2.client import Client
from flowbio.v2.samples import MetadataAttribute, SampleTypeId


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
                    name=f"{attribute.identifier}__annotation",
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
