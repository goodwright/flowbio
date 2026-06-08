"""Shared fixtures for the CLI test suite.

The CLI is exercised in-process: a test invokes :func:`run_cli` with an explicit
argv list and asserts on the captured stdout/stderr and the returned exit code.
The HTTP layer is mocked per-test with ``respx`` (the existing project stack),
mirroring ``tests/unit/v2/conftest.py``.
"""
from __future__ import annotations

import contextlib
import io
from dataclasses import dataclass
from typing import Callable

import pytest

DEFAULT_BASE_URL = "https://app.flow.bio/api"


@dataclass(frozen=True)
class CliResult:
    """Captured outcome of an in-process CLI invocation."""

    exit_code: int
    stdout: str
    stderr: str


@pytest.fixture
def run_cli() -> Callable[..., CliResult]:
    """Return a helper that runs the CLI in-process and captures its output.

    ``main`` is imported lazily inside the helper so the fixture can be
    collected before the CLI package exists (test-first development), and any
    stray ``SystemExit`` from argparse is translated to an exit code so callers
    always receive a :class:`CliResult`.
    """

    def _run(*argv: str) -> CliResult:
        from flowbio.cli._main import main

        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                exit_code = main(list(argv))
            except SystemExit as exit_signal:
                exit_code = _exit_code_from_signal(exit_signal.code)
        return CliResult(
            exit_code=exit_code,
            stdout=out.getvalue(),
            stderr=err.getvalue(),
        )

    return _run


def _exit_code_from_signal(code: object) -> int:
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    return 1
