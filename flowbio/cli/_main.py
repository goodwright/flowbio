"""Entry point and command dispatch for the ``flowbio`` CLI.

Parses argv with the tree built in :mod:`flowbio.cli._parser`, then dispatches
to the selected domain handler with a constructed :class:`~flowbio.v2.Client`
injected. All cross-cutting concerns — credential resolution, output rendering,
exit-code mapping, progress — are delegated to the sibling ``_``-prefixed
modules.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from flowbio.cli._auth import resolve_credentials
from flowbio.cli._exit_codes import CliUsageError, ExitCode, exit_code_for
from flowbio.cli._output import Output
from flowbio.cli._parser import build_parser
from flowbio.cli._progress import progress_config
from flowbio.cli._types import BaseUrl, Token
from flowbio.v2.client import Client
from flowbio.v2.exceptions import FlowApiError

# A handler runs one command against an authenticated client and returns the
# process exit code. Errors are raised (not returned) and mapped centrally.
Handler = Callable[[argparse.Namespace, Client, Output], ExitCode]


@dataclass(frozen=True)
class GlobalOptions:
    """The cross-cutting options shared by every command, in their named types."""

    json: bool
    no_progress: bool
    token: Token | None
    token_file: Path | None
    base_url: BaseUrl | None
    force_login: bool
    username: str | None


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return a process exit code.

    :param argv: Arguments to parse (defaults to ``sys.argv[1:]``).
    :returns: A stable :class:`~flowbio.cli._exit_codes.ExitCode` value.
    """
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as exit_signal:
        # argparse exits 0 for --help/--version and 2 for parse errors.
        return _coerce_exit_code(exit_signal.code)

    # argparse always sets `resource`; once a resource is engaged it also sets
    # `verb` (to None if omitted), so direct access is safe after the guard.
    if args.resource is None:
        parser.print_help(sys.stderr)
        return int(ExitCode.USAGE)
    if args.verb is None:
        args.command_parser.print_help(sys.stderr)
        return int(ExitCode.USAGE)

    return _dispatch(args)


def _dispatch(args: argparse.Namespace) -> int:
    options = _extract_global_options(args)
    output = Output(json_mode=options.json, stdout=sys.stdout, stderr=sys.stderr)
    handler: Handler = args.handler
    try:
        resolved = resolve_credentials(
            token=options.token,
            token_file=options.token_file,
            base_url=options.base_url,
            force_login=options.force_login,
            username=options.username,
        )
        client = Client(
            base_url=resolved.base_url,
            config=progress_config(options.no_progress),
        )
        client.log_in(resolved.credentials)
        return int(handler(args, client, output))
    except CliUsageError as error:
        output.emit_error(str(error))
        return int(ExitCode.USAGE)
    except FlowApiError as error:
        output.emit_error(error.message, status_code=error.status_code)
        return int(exit_code_for(error))


def _extract_global_options(args: argparse.Namespace) -> GlobalOptions:
    # getattr with a default is required because the global options use
    # default=argparse.SUPPRESS: an attribute is absent unless the user passed
    # it, which is what lets the options appear before or after the verb.
    token = getattr(args, "token", None)
    token_file = getattr(args, "token_file", None)
    base_url = getattr(args, "base_url", None)
    return GlobalOptions(
        json=getattr(args, "json", False),
        no_progress=getattr(args, "no_progress", False),
        token=Token(token) if token is not None else None,
        token_file=Path(token_file) if token_file is not None else None,
        base_url=BaseUrl(base_url) if base_url is not None else None,
        force_login=getattr(args, "login", False),
        username=getattr(args, "username", None),
    )


def _coerce_exit_code(code: int | str | None) -> int:
    if code is None:
        return int(ExitCode.SUCCESS)
    if isinstance(code, int):
        return code
    return int(ExitCode.RUNTIME)
