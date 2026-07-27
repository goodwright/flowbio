"""CSV accession-sheet parsing and pre-flight validation for ``samples import``.

An accession sheet is a CSV with one row per accession to import: an
``accession`` column (a public-repository run or experiment accession) plus
optional ``name``/``organism`` and per-accession metadata columns. This
mirrors ``_sheet.py``'s reads-based sample sheet, but the reserved columns
differ — there is nothing to upload (no ``reads1``/``reads2``) and the import
API has no project field, so ``RESERVED_COLUMNS`` is ``accession``, ``name``,
``organism`` instead.
"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from pathlib import Path

from flowbio.cli._exit_codes import CliUsageError
from flowbio.cli._files import existing_file
from flowbio.cli._sheet import metadata_errors
from flowbio.v2.samples import MetadataAttribute, SampleTypeId

RESERVED_COLUMNS = ("accession", "name", "organism")

# Mirrors the API's own accession format rule (one run or experiment accession
# per entry), so a malformed accession is reported up front like every other
# validation problem instead of failing the whole batch request server-side.
_SUPPORTED_ACCESSION = re.compile(r"^[SED]R[RX]\d+$")


@dataclass(frozen=True)
class AccessionSheetRow:
    """One data row of an accession sheet.

    ``accession`` may be empty (empty cell) — that is reported by
    :func:`validate_accession_row` rather than rejected here, so all errors
    surface together.
    """

    row_number: int
    accession: str
    name: str | None
    organism: str | None
    metadata: dict[str, str]


@dataclass(frozen=True)
class AccessionSheet:
    """A parsed accession sheet."""

    path: Path
    metadata_columns: list[str]
    rows: list[AccessionSheetRow]


def parse_accession_sheet(path: Path) -> AccessionSheet:
    """Parse a CSV accession sheet into an :class:`AccessionSheet`.

    :param path: The accession-sheet file. Must be a ``.csv`` — an ``.xlsx`` or
        ``.tsv`` is a usage error directing the user to export to CSV.
    :returns: The parsed sheet with reserved/metadata columns separated,
        accessions normalised to upper case, and empty cells dropped.
    :raises CliUsageError: If the file is not a readable ``.csv``.
    """
    if path.suffix.lower() != ".csv":
        raise CliUsageError(
            f"Accession sheet must be a .csv file: {path}. "
            f"Export your spreadsheet to CSV first.",
        )
    existing_file(path)
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        metadata_columns = [
            header for header in headers if header not in RESERVED_COLUMNS
        ]
        rows = [
            _build_row(record, row_number, metadata_columns)
            for row_number, record in enumerate(reader, start=1)
        ]
    return AccessionSheet(path=path, metadata_columns=metadata_columns, rows=rows)


def validate_accession_row(
    row: AccessionSheetRow,
    attributes: list[MetadataAttribute],
    sample_type: SampleTypeId,
) -> list[str]:
    """Return every validation problem on ``row`` (empty when the row is valid).

    :param row: The parsed row to validate.
    :param attributes: The server's metadata attributes, deciding required and
        closed-option columns.
    :param sample_type: The sample type applied to the whole import; an
        attribute required for it must be present.
    :returns: One human-readable message per problem, collected so the caller
        can report them all at once.
    """
    errors: list[str] = []
    if not row.accession:
        errors.append("missing required value: accession")
    elif not _SUPPORTED_ACCESSION.match(row.accession):
        errors.append(
            f"'{row.accession}' is not a supported accession — import one run "
            f"(SRR/ERR/DRR) or experiment (SRX/ERX/DRX) accession per row",
        )
    errors.extend(metadata_errors(row.metadata, attributes, sample_type))
    return errors


def duplicate_accession_errors(rows: list[AccessionSheetRow]) -> dict[int, list[str]]:
    """Return extra errors for rows whose accession repeats an earlier row.

    Mirrors the API's own duplicate-accession rejection so a sheet with
    repeats is reported up front, in the same per-row shape as every other
    validation problem, rather than surfacing as one opaque batch failure.

    :param rows: Every row in the sheet, including ones already found invalid.
    :returns: A mapping of ``row_number`` to the duplicate-accession messages
        for rows after the first occurrence of a repeated accession. Rows with
        a blank accession (already reported by :func:`validate_accession_row`)
        are never flagged as duplicates of each other.
    """
    first_seen: dict[str, int] = {}
    errors: dict[int, list[str]] = {}
    for row in rows:
        if not row.accession:
            continue
        if row.accession in first_seen:
            errors.setdefault(row.row_number, []).append(
                f"duplicate accession '{row.accession}' "
                f"(first seen at row {first_seen[row.accession]})",
            )
        else:
            first_seen[row.accession] = row.row_number
    return errors


def _build_row(
    record: dict[str, str], row_number: int, metadata_columns: list[str],
) -> AccessionSheetRow:
    def cell(column: str) -> str | None:
        value = (record.get(column) or "").strip()
        return value or None

    metadata = {
        column: value
        for column in metadata_columns
        if (value := (record.get(column) or "").strip())
    }
    accession = cell("accession")
    return AccessionSheetRow(
        row_number=row_number,
        accession=accession.upper() if accession else "",
        name=cell("name"),
        organism=cell("organism"),
        metadata=metadata,
    )
