"""Output rendering for both humans and automated agents (FR-035…FR-037).

In human mode, results are concise lines on stdout while advisories and errors
go to stderr. In ``--json`` mode, exactly one JSON document is written to stdout
and nothing else; errors instead become a JSON document on stderr carrying the
message and, where applicable, the HTTP status code. Keeping stdout clean under
``--json`` lets agents pipe it straight into a parser.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TextIO


@dataclass(frozen=True)
class Output:
    """Renders command results, advisories, and errors to the right stream.

    :param json_mode: When ``True``, emit machine-readable JSON; otherwise emit
        human-readable lines.
    :param stdout: The stream for results (and JSON documents).
    :param stderr: The stream for advisories, progress, and errors.
    """

    json_mode: bool
    stdout: TextIO
    stderr: TextIO

    def emit_result(self, human_line: str, document: object) -> None:
        """Emit a successful command result.

        :param human_line: The concise line shown in human mode.
        :param document: The JSON-serialisable value shown in ``--json`` mode as
            the single stdout document.
        """
        if self.json_mode:
            print(json.dumps(document), file=self.stdout)
        else:
            print(human_line, file=self.stdout)

    def emit_advisory(self, message: str) -> None:
        """Emit human-readable advisory text to stderr.

        Suppressed under ``--json`` so stdout stays a single clean document.

        :param message: The advisory text (e.g. a required-columns summary).
        """
        if not self.json_mode:
            print(message, file=self.stderr)

    def emit_error(self, message: object, status_code: int | None = None) -> None:
        """Emit an error to stderr.

        :param message: The error message — a string, or a structured value
            (e.g. the library's field-level error dict) preserved as-is in JSON.
        :param status_code: The HTTP status code, when the error came from the
            server. Included in the JSON document where present.
        """
        if self.json_mode:
            document: dict[str, object] = {"message": message}
            if status_code is not None:
                document["status_code"] = int(status_code)
            print(json.dumps(document), file=self.stderr)
        else:
            print(f"Error: {message}", file=self.stderr)
