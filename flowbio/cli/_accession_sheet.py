"""CSV accession-sheet parsing for ``samples import``.

An accession sheet is a CSV with one row per accession to import: a required
``accession`` column (a public-repository run or experiment accession) plus
optional ``name``/``organism``/``sample_type`` and per-accession metadata
columns. This mirrors ``_sheet.py``'s reads-based sample sheet, but the
reserved columns differ — there is nothing to upload (no ``reads1``/
``reads2``) and the import API has no project field.

Domain rules (accession format, duplicates, sample type, organism, metadata)
are all checked server-side when the sheet is submitted — duplicating that
locally would just be a second, driftable copy of the same rules. An
accession is different: it is the one column every row must have to mean
anything at all, so a missing one is rejected here rather than silently
skipped or shipped as an empty string the server would just reject anyway.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from flowbio.cli._exit_codes import CliUsageError
from flowbio.cli._files import existing_file
from flowbio.v2.samples import SampleImportSpec, SampleTypeId

RESERVED_COLUMNS = ("accession", "name", "organism", "sample_type")


@dataclass(frozen=True)
class AccessionSheetRow:
    """One data row of an accession sheet.

    ``sample_type`` is only set when the sheet has its own ``sample_type``
    column for this row; :meth:`to_spec` falls back to the batch's
    ``--sample-type`` when it's absent.
    """

    row_number: int
    accession: str
    name: str | None
    organism: str | None
    sample_type: SampleTypeId | None
    metadata: dict[str, str]

    def __post_init__(self) -> None:
        if not self.accession:
            raise ValueError("accession must not be empty")

    def to_spec(self, default_sample_type: SampleTypeId) -> SampleImportSpec:
        """Build the :class:`~flowbio.v2.samples.SampleImportSpec` for this row.

        :param default_sample_type: The sample type to use when this row has
            no ``sample_type`` of its own.
        """
        return SampleImportSpec(
            accession=self.accession,
            sample_type=self.sample_type or default_sample_type,
            name=self.name,
            organism_id=self.organism,
            metadata=self.metadata or None,
        )


@dataclass(frozen=True)
class AccessionSheet:
    """A parsed accession sheet."""

    path: Path
    rows: list[AccessionSheetRow]


def parse_accession_sheet(path: Path) -> AccessionSheet:
    """Parse a CSV accession sheet into an :class:`AccessionSheet`.

    :param path: The accession-sheet file. Must be a ``.csv`` — an ``.xlsx`` or
        ``.tsv`` is a usage error directing the user to export to CSV.
    :returns: The parsed sheet, with empty cells dropped. Values are otherwise
        passed through unchanged — including ``accession``, sent to the
        server exactly as entered.
    :raises CliUsageError: If the file is not a readable ``.csv``, has no
        rows, or has a row with no accession.
    """
    if path.suffix.lower() != ".csv":
        raise CliUsageError(
            f"Accession sheet must be a .csv file: {path}. "
            f"Export your spreadsheet to CSV first.",
        )
    existing_file(path)
    # utf-8-sig transparently strips a leading BOM, which spreadsheet tools
    # (notably Excel's "CSV UTF-8" export) prepend — otherwise the first header
    # parses as "﻿accession" and every row reports a missing accession.
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        metadata_columns = [
            header for header in headers if header not in RESERVED_COLUMNS
        ]
        records = list(enumerate(reader, start=1))
    if not records:
        raise CliUsageError(f"Accession sheet has no rows: {path}.")
    missing = [
        row_number for row_number, record in records if not _cell(record, "accession")
    ]
    if missing:
        numbers = ", ".join(str(number) for number in missing)
        # Data row 1 is the first row after the header, matching _sheet.py's
        # convention (and upload-batch's documented "1-based row number").
        verb = "has" if len(missing) == 1 else "have"
        raise CliUsageError(
            f"Accession sheet data row(s) {numbers} {verb} no accession: {path}.",
        )
    # The walrus filter is a no-op here: parse_accession_sheet already raised
    # above if any record lacked an accession. Filtering on it (rather than
    # asserting) is what gives the accession its narrowed str type below.
    rows = [
        _build_row(record, row_number, metadata_columns, accession)
        for row_number, record in records
        if (accession := _cell(record, "accession")) is not None
    ]
    return AccessionSheet(path=path, rows=rows)


def _cell(record: dict[str, str], column: str) -> str | None:
    value = (record.get(column) or "").strip()
    return value or None


def _build_row(
    record: dict[str, str], row_number: int, metadata_columns: list[str], accession: str,
) -> AccessionSheetRow:
    metadata = {
        column: value
        for column in metadata_columns
        if (value := _cell(record, column)) is not None
    }
    sample_type = _cell(record, "sample_type")
    return AccessionSheetRow(
        row_number=row_number,
        accession=accession,
        name=_cell(record, "name"),
        organism=_cell(record, "organism"),
        sample_type=SampleTypeId(sample_type) if sample_type is not None else None,
        metadata=metadata,
    )
