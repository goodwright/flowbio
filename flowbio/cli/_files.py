"""Local-file validation shared by the upload commands.

A missing or unreadable input path is a caller mistake, not a server failure, so
it surfaces as a :class:`~flowbio.cli._exit_codes.CliUsageError` (exit ``2``)
with a clean message rather than letting an ``OSError`` escape as a traceback.
"""
from __future__ import annotations

from pathlib import Path

from flowbio.cli._exit_codes import CliUsageError


def existing_file(path: Path) -> Path:
    """Return ``path`` if it is an existing file, else raise ``CliUsageError``.

    :param path: The local path to validate.
    :returns: The same path, once confirmed to be a readable file.
    :raises CliUsageError: If the path does not point at an existing file.
    """
    if not path.is_file():
        raise CliUsageError(f"File not found: {path}")
    return path
