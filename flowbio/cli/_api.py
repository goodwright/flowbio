"""The ``flowbio api`` command group — read-only API passthrough.

A single ``api get <path>`` verb issues a GET to an arbitrary path under the
configured base URL and writes the response body to stdout verbatim, so a
caller can pipe it straight through ``jq``. It uses a token when one is
available and otherwise reads anonymously. The command is GET-only by
construction, so it cannot mutate remote state.
"""
from __future__ import annotations

import argparse

from flowbio.cli._exit_codes import CliUsageError, ExitCode
from flowbio.cli._output import Output
from flowbio.v2.client import Client


def register(
    resource: argparse.ArgumentParser, global_parent: argparse.ArgumentParser,
) -> None:
    """Register the ``api`` verbs on the resource parser."""
    verbs = resource.add_subparsers(dest="verb", metavar="<verb>")
    get = verbs.add_parser(
        "get",
        parents=[global_parent],
        help="Issue a GET to an API path and print the raw response body.",
        description=(
            "Issue a GET to a path under the Flow API base URL and write the "
            "raw response body to stdout. Uses a token when one is available, "
            "otherwise reads anonymously (public resources only)."
        ),
    )
    get.set_defaults(command_parser=get, handler=_get_command, allow_anonymous=True)
    get.add_argument(
        "path",
        metavar="PATH",
        help="API path relative to the base URL, e.g. /samples/search.",
    )
    get.add_argument(
        "--param",
        metavar="KEY=VALUE",
        action="append",
        help="Query parameter (repeatable); the value is URL-encoded.",
    )


def _get_command(args: argparse.Namespace, client: Client, output: Output) -> ExitCode:
    """Issue the GET and write the raw response body to stdout.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` on success.
    :raises CliUsageError: If the path carries a query string or a
        ``--param`` value is missing its ``=``.
    """
    if "?" in args.path:
        raise CliUsageError(
            "Query parameters go in --param KEY=VALUE, not the path.",
        )
    params = _parse_params(args.param)
    output.emit_raw(client.get_raw(args.path, params=params))
    return ExitCode.SUCCESS


def _parse_params(raw: list[str] | None) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for item in raw or []:
        key, sep, value = item.partition("=")
        if not sep:
            raise CliUsageError(
                f"--param must be KEY=VALUE, got {item!r}.",
            )
        pairs.append((key, value))
    return pairs
