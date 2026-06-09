"""The ``flowbio samples`` command group (FR-016…FR-019).

A thin wrapper over :attr:`Client.samples <flowbio.v2.Client.samples>`: it parses
the command line, merges metadata supplied as ``key=value`` pairs and/or a JSON
object, calls the library, and renders the result. The ``--sample-type`` is sent
as-is and validated server-side, not pre-checked by the CLI.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from flowbio.cli._exit_codes import CliUsageError, ExitCode
from flowbio.cli._files import existing_file
from flowbio.cli._output import Output
from flowbio.v2.client import Client


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
        help="Sample type identifier (sent as-is; validated server-side).",
    )
    upload.add_argument(
        "--reads1",
        required=True,
        metavar="PATH",
        help="First reads file.",
    )
    upload.add_argument(
        "--reads2",
        metavar="PATH",
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
        help=(
            "Sample type identifier (sent as-is; validated server-side). "
            "Defaults to 'generic' (base columns common to all types)."
        ),
    )
    annotation_template.add_argument(
        "-o",
        "--output",
        metavar="PATH",
        help="File to write the .xlsx workbook to. Required when stdout is a terminal.",
    )


def _configure_upload_multiplexed(upload_multiplexed: argparse.ArgumentParser) -> None:
    upload_multiplexed.set_defaults(
        command_parser=upload_multiplexed, handler=_upload_multiplexed_command,
    )
    upload_multiplexed.add_argument(
        "--reads1",
        required=True,
        metavar="PATH",
        help="First multiplexed reads file.",
    )
    upload_multiplexed.add_argument(
        "--reads2",
        metavar="PATH",
        help="Second multiplexed reads file (makes the upload paired-end).",
    )
    upload_multiplexed.add_argument(
        "--annotation",
        required=True,
        metavar="PATH",
        help="Completed annotation sheet (obtained via `annotation-template`).",
    )
    upload_multiplexed.add_argument(
        "--reject-warnings",
        action="store_true",
        help="Reject the upload if the annotation sheet has warnings.",
    )


def _upload_command(args: argparse.Namespace, client: Client, output: Output) -> ExitCode:
    """Upload a single sample and report its identifier.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` on success.
    """
    metadata = _merge_metadata(args.metadata, args.metadata_json)
    data = {"reads1": existing_file(Path(args.reads1))}
    if args.reads2 is not None:
        data["reads2"] = existing_file(Path(args.reads2))
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
    destination = Path(args.output) if args.output is not None else None
    if destination is None and (output.json_mode or output.stdout.isatty()):
        raise CliUsageError(
            "The annotation template is a binary workbook; pass -o/--output PATH.",
        )
    template = client.samples.get_annotation_template(args.sample_type)
    if destination is None:
        output.stdout.buffer.write(template)
        output.emit_advisory(
            f"Wrote {args.sample_type} annotation template to standard output",
        )
        return ExitCode.SUCCESS
    destination.write_bytes(template)
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
    reads = {"reads1": existing_file(Path(args.reads1))}
    if args.reads2 is not None:
        reads["reads2"] = existing_file(Path(args.reads2))
    upload = client.samples.upload_multiplexed_data(
        reads=reads,
        annotation=existing_file(Path(args.annotation)),
        ignore_warnings=not args.reject_warnings,
    )
    if upload.warnings:
        output.emit_advisory(f"Annotation warnings: {upload.warnings}")
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
