"""The ``flowbio`` command-line interface.

A thin presentation layer over :mod:`flowbio.v2` that exposes the upload
operations from the terminal for both humans (concise lines) and automated
agents (``--json`` output with stable exit codes).

The public surface is the command line itself, documented in ``docs/cli.md``.
All modules in this package are internal: domain handlers (:mod:`flowbio.cli.data`,
:mod:`flowbio.cli.samples`) receive a constructed :class:`~flowbio.v2.Client`,
while ``_``-prefixed modules hold the cross-cutting infrastructure (argument
parsing, credential resolution, output rendering, exit-code mapping, progress,
and sample-sheet parsing).
"""
