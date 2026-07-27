"""CSV accession-sheet parsing for ``samples import``.

An accession sheet is a CSV with one row per accession to import: an
``accession`` column (a public-repository run or experiment accession) plus
optional ``name``/``organism`` and per-accession metadata columns. This
mirrors ``_sheet.py``'s reads-based sample sheet, but the reserved columns
differ — there is nothing to upload (no ``reads1``/``reads2``) and the import
API has no project field, so ``RESERVED_COLUMNS`` is ``accession``, ``name``,
``organism`` instead.

Rows are not validated here: the accession format, duplicates, sample type,
organism, and metadata rules are all checked server-side when the sheet is
submitted — duplicating that locally would just be a second, driftable copy
of the same rules.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from flowbio.cli._exit_codes import CliUsageError
from flowbio.cli._files import existing_file

RESERVED_COLUMNS = ("accession", "name", "organism")


@dataclass(frozen=True)
class AccessionSheetRow:
    """One data row of an accession sheet."""

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
