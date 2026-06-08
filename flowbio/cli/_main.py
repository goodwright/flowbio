"""Top-level argument parser and command dispatch for the ``flowbio`` CLI.

Builds a ``flowbio <resource> <verb>`` argparse tree where the global options
(``--json``, ``--token``, …) are accepted identically before *and* after the
verb (FR-004), then dispatches to the selected domain handler with a constructed
:class:`~flowbio.v2.Client` injected. All cross-cutting concerns — credential
resolution, output rendering, exit-code mapping, progress — are delegated to the
sibling ``_``-prefixed modules.
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Callable

from flowbio.cli._auth import resolve_credentials
from flowbio.cli._exit_codes import CliUsageError, ExitCode, exit_code_for
from flowbio.cli._output import Output
from flowbio.cli._progress import progress_config
from flowbio.v2.client import Client
from flowbio.v2.exceptions import FlowApiError

# A handler runs one command against an authenticated client and returns the
# process exit code. Errors are raised (not returned) and mapped centrally.
Handler = Callable[[argparse.Namespace, Client, Output], ExitCode]


@dataclass(frozen=True)
class GlobalOptions:
    """The cross-cutting options shared by every command."""

    json: bool
    no_progress: bool
    token: str | None
    token_file: str | None
    base_url: str | None
    login: bool
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

    if getattr(args, "resource", None) is None:
        parser.print_help(sys.stderr)
        return int(ExitCode.USAGE)
    if getattr(args, "verb", None) is None:
        args.command_parser.print_help(sys.stderr)
        return int(ExitCode.USAGE)

    return _dispatch(args)


def build_parser() -> argparse.ArgumentParser:
    """Construct the full argument-parser tree.

    Exposed for tests that inspect parsing behaviour directly.
    """
    global_parent = _build_global_parent()

    parser = argparse.ArgumentParser(
        prog="flowbio",
        description="Upload data and samples to the Flow platform.",
        parents=[global_parent],
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"flowbio {_resolve_version()}",
    )
    parser.set_defaults(command_parser=parser)

    resources = parser.add_subparsers(dest="resource", metavar="<resource>")

    data_parser = resources.add_parser(
        "data",
        parents=[global_parent],
        help="Generic data-file operations.",
        description="Upload generic data files to the Flow platform.",
    )
    data_parser.set_defaults(command_parser=data_parser)
    data_verbs = data_parser.add_subparsers(dest="verb", metavar="<verb>")
    _register_data_commands(data_verbs, global_parent)

    samples_parser = resources.add_parser(
        "samples",
        parents=[global_parent],
        help="Sample operations (upload, templates, batches).",
        description="Upload and manage sequencing samples on the Flow platform.",
    )
    samples_parser.set_defaults(command_parser=samples_parser)
    samples_verbs = samples_parser.add_subparsers(dest="verb", metavar="<verb>")
    _register_samples_commands(samples_verbs, global_parent)

    return parser


def _build_global_parent() -> argparse.ArgumentParser:
    # default=SUPPRESS so an option set on one level (before or after the verb)
    # is never overwritten by the other level's default — the FR-004 mechanism.
    parent = argparse.ArgumentParser(add_help=False)
    parent.add_argument(
        "--json",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Emit one JSON document on stdout (machine-readable mode).",
    )
    parent.add_argument(
        "--no-progress",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Disable upload progress output.",
    )
    parent.add_argument(
        "--token",
        metavar="TOKEN",
        default=argparse.SUPPRESS,
        help="API token to authenticate with (or set FLOW_API_TOKEN).",
    )
    parent.add_argument(
        "--token-file",
        metavar="PATH",
        default=argparse.SUPPRESS,
        help="Read the API token from this file (or set FLOW_TOKEN_FILE).",
    )
    parent.add_argument(
        "--base-url",
        metavar="URL",
        default=argparse.SUPPRESS,
        help="Override the Flow API base URL (or set FLOW_API_URL).",
    )
    parent.add_argument(
        "--login",
        action="store_true",
        default=argparse.SUPPRESS,
        help="Force interactive username/password login.",
    )
    parent.add_argument(
        "--username",
        metavar="NAME",
        default=argparse.SUPPRESS,
        help="Username for --login (the password is always prompted).",
    )
    return parent


def _register_data_commands(
    verbs: argparse._SubParsersAction, global_parent: argparse.ArgumentParser,
) -> None:
    """Register ``data`` verbs."""
    from flowbio.cli.data import register

    register(verbs, global_parent)


def _register_samples_commands(
    verbs: argparse._SubParsersAction, global_parent: argparse.ArgumentParser,
) -> None:
    """Register ``samples`` verbs. Filled in per user-story phase."""


def _dispatch(args: argparse.Namespace) -> int:
    options = _extract_global_options(args)
    output = Output(json_mode=options.json, stdout=sys.stdout, stderr=sys.stderr)
    handler: Handler = args.handler
    try:
        resolved = resolve_credentials(
            token=options.token,
            token_file=options.token_file,
            base_url=options.base_url,
            login=options.login,
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
    return GlobalOptions(
        json=getattr(args, "json", False),
        no_progress=getattr(args, "no_progress", False),
        token=getattr(args, "token", None),
        token_file=getattr(args, "token_file", None),
        base_url=getattr(args, "base_url", None),
        login=getattr(args, "login", False),
        username=getattr(args, "username", None),
    )


def _coerce_exit_code(code: object) -> int:
    if code is None:
        return int(ExitCode.SUCCESS)
    if isinstance(code, int):
        return code
    return int(ExitCode.RUNTIME)


def _resolve_version() -> str:
    try:
        return version("flowbio")
    except PackageNotFoundError:
        return "unknown"
