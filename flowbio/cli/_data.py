"""The ``flowbio data`` command group (FR-014, FR-015).

A thin wrapper over :attr:`Client.data <flowbio.v2.Client.data>`: it parses the
command line, calls the library, and renders the result. The ``--data-type`` is
sent as-is and validated server-side, not pre-checked by the CLI.
"""
from __future__ import annotations

import argparse
from pathlib import Path

from flowbio.cli._exit_codes import ExitCode
from flowbio.cli._files import existing_file
from flowbio.cli._output import Output
from flowbio.v2.client import Client


def register(
    resource: argparse.ArgumentParser, global_parent: argparse.ArgumentParser,
) -> None:
    """Register the ``data`` verbs on the resource parser."""
    verbs = resource.add_subparsers(dest="verb", metavar="<verb>")
    upload = verbs.add_parser(
        "upload",
        parents=[global_parent],
        help="Upload a generic data file.",
        description="Upload a generic data file to the Flow platform.",
    )
    upload.set_defaults(command_parser=upload, handler=_upload_command)
    upload.add_argument(
        "path",
        metavar="PATH",
        help="Local file to upload.",
    )
    upload.add_argument(
        "--filename",
        metavar="NAME",
        help="Override the name the file is stored under on Flow.",
    )
    upload.add_argument(
        "--data-type",
        metavar="TYPE",
        help="Optional data-type identifier (sent as-is; validated server-side).",
    )
    upload.add_argument(
        "--directory",
        action="store_true",
        help="Upload PATH as a directory archive (.zip/.tar/.tar.gz).",
    )


def _upload_command(args: argparse.Namespace, client: Client, output: Output) -> ExitCode:
    """Upload a generic data file and report its identifier.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` on success.
    """
    data = client.data.upload_data(
        existing_file(Path(args.path)),
        filename=args.filename,
        data_type=args.data_type,
        is_directory=args.directory,
    )
    output.emit_result(f"Uploaded data {data.id}", {"id": data.id})
    return ExitCode.SUCCESS
