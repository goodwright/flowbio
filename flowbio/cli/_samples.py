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
    upload = verbs.add_parser(
        "upload",
        parents=[global_parent],
        help="Upload a single demultiplexed sample.",
        description="Upload a single demultiplexed sample to the Flow platform.",
    )
    upload.set_defaults(command_parser=upload, handler=_upload_command)
    upload.add_argument(
        "--name",
        required=True,
        metavar="NAME",
        help="Sample name (must not contain spaces).",
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
        if not separator:
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
    return {str(key): str(value) for key, value in parsed.items()}
