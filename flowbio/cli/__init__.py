"""The ``flowbio`` command-line interface.

A thin presentation layer over :mod:`flowbio.v2` that exposes the upload
operations from the terminal for both humans (concise lines) and automated
agents (``--json`` output with stable exit codes).

The public surface is the command line itself, documented in ``docs/cli.md``;
the package's only public Python symbol is :func:`main`, the console-script
entry point. All modules are internal: domain command modules
(:mod:`flowbio.cli._data`, :mod:`flowbio.cli._samples`) are imported only by the
parser, while the other ``_``-prefixed modules hold the cross-cutting
infrastructure (argument parsing, credential resolution, output rendering,
exit-code mapping, progress, and sample-sheet parsing).
"""
from flowbio.cli._main import main

__all__ = ["main"]
