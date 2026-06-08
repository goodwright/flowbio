"""Construction of the ``flowbio`` argument-parser tree.

Builds a ``flowbio <resource> <verb>`` tree where the global options
(``--json``, ``--token``, …) are accepted identically before *and* after the
verb (FR-004): they live on a shared parent parser attached to both the
top-level parser and every leaf, with ``default=argparse.SUPPRESS`` so a value
set on one level is never overwritten by the other level's default. Dispatch on
the parsed result lives in :mod:`flowbio.cli._main`.
"""
from __future__ import annotations

import argparse
from importlib.metadata import PackageNotFoundError, version

from flowbio.cli._data import register as register_data


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
    register_data(verbs, global_parent)


def _register_samples_commands(
    verbs: argparse._SubParsersAction, global_parent: argparse.ArgumentParser,
) -> None:
    """Register ``samples`` verbs. Filled in per user-story phase."""


def _resolve_version() -> str:
    try:
        return version("flowbio")
    except PackageNotFoundError:
        return "unknown"
