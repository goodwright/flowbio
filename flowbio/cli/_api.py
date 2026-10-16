"""The ``flowbio api`` command group — raw API passthrough.

``api get <path>`` issues a GET to an arbitrary path under the configured base
URL and writes the response body to stdout verbatim, so a caller can pipe it
straight through ``jq``. It uses a token when one is available and otherwise
reads anonymously. ``api post`` and ``api patch`` send a JSON body the same way
but always require credentials, never falling back to an anonymous request.
There is deliberately no ``delete`` verb, so the passthrough cannot remove
remote state.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from flowbio.cli._exit_codes import CliUsageError, ExitCode
from flowbio.cli._files import existing_file
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
    _register_write_verb(verbs, "post", global_parent, Client.post_raw)
    _register_write_verb(verbs, "patch", global_parent, Client.patch_raw)


def _register_write_verb(
    verbs: argparse._SubParsersAction[argparse.ArgumentParser],
    name: str,
    global_parent: argparse.ArgumentParser,
    send: Callable[[Client, str, bytes], str],
) -> None:
    method = name.upper()
    verb = verbs.add_parser(
        name,
        parents=[global_parent],
        help=f"Issue a {method} with a JSON body and print the raw response body.",
        description=(
            f"Issue a {method} with a JSON body to a path under the Flow API "
            "base URL and write the raw response body to stdout. The body is "
            "sent unchanged and validated by the server; see /v2/reference for "
            "each operation's body. Requires credentials; never anonymous."
        ),
    )
    verb.set_defaults(command_parser=verb, handler=_write_command, send=send)
    verb.add_argument(
        "path",
        metavar="PATH",
        help="API path relative to the base URL, e.g. /v2/projects.",
    )
    verb.add_argument(
        "--body",
        metavar="FILE|-",
        required=True,
        help="File holding the JSON request body, or - to read it from stdin.",
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


def _write_command(args: argparse.Namespace, client: Client, output: Output) -> ExitCode:
    """Send the JSON body and write the raw response body to stdout.

    :param args: Parsed command-line arguments.
    :param client: The authenticated Flow client.
    :param output: The result/error renderer.
    :returns: :attr:`ExitCode.SUCCESS` on success.
    :raises CliUsageError: If the ``--body`` file does not exist.
    """
    output.emit_raw(args.send(client, args.path, _read_body(args.body)))
    return ExitCode.SUCCESS


def _read_body(source: str) -> bytes:
    if source == "-":
        return sys.stdin.buffer.read()
    return existing_file(Path(source)).read_bytes()
