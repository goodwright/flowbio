"""The CLI's stable exit-code contract.

Every command returns one of these codes so that callers — humans and automated
agents alike — can branch on the outcome (FR-038). Library failures are mapped
from the :class:`~flowbio.v2.exceptions.FlowApiError` hierarchy in one place
(:func:`exit_code_for`); usage problems detected by the CLI itself are signalled
by raising :class:`CliUsageError`.
"""
from __future__ import annotations

from enum import IntEnum

from flowbio.v2.exceptions import (
    AuthenticationError,
    BadRequestError,
    FlowApiError,
    NotFoundError,
)


class ExitCode(IntEnum):
    """Process exit codes returned by every ``flowbio`` command."""

    SUCCESS = 0
    RUNTIME = 1
    USAGE = 2
    AUTH = 3
    NOT_FOUND = 4
    BAD_REQUEST = 5


class CliUsageError(Exception):
    """Raised for a usage, configuration, or input error detected by the CLI.

    Distinct from the library's :class:`~flowbio.v2.exceptions.FlowApiError`
    hierarchy: this signals a problem with how the command was invoked (e.g.
    conflicting flags, a missing token file, a non-CSV sample sheet) rather than
    a server response. Always maps to :attr:`ExitCode.USAGE`.
    """


def exit_code_for(exc: Exception) -> ExitCode:
    """Map an exception to its stable :class:`ExitCode` (FR-038).

    :param exc: The exception raised while running a command.
    :returns: The exit code to return to the caller.
    """
    if isinstance(exc, CliUsageError):
        return ExitCode.USAGE
    if isinstance(exc, AuthenticationError):
        return ExitCode.AUTH
    if isinstance(exc, NotFoundError):
        return ExitCode.NOT_FOUND
    # AnnotationValidationError is a BadRequestError subclass, so it is covered.
    if isinstance(exc, BadRequestError):
        return ExitCode.BAD_REQUEST
    if isinstance(exc, FlowApiError):
        return ExitCode.RUNTIME
    return ExitCode.RUNTIME
