"""CSV accession-sheet parsing for ``samples import``.

An accession sheet is a CSV with one row per accession to import: required
``accession`` and ``sample_type`` columns, plus optional ``name``/
``organism`` and per-accession metadata columns. This mirrors ``_sheet.py``'s
reads-based sample sheet, but the reserved columns differ — there is nothing
to upload (no ``reads1``/``reads2``) and the import API has no project field.

Domain rules (accession format, duplicates, sample type, organism, metadata)
are all checked server-side when the sheet is submitted — duplicating that
locally would just be a second, driftable copy of the same rules.
``accession`` and ``sample_type`` are different: they are the two columns
every row must have to mean anything at all, so a missing one is rejected
here rather than silently skipped or shipped as an empty string the server
would just reject anyway. There is deliberately no other way to supply a
sample type for ``samples import`` — the sheet is the single source of it.
A row with every cell blank (e.g. a trailing comma-only line some spreadsheet
exports append below the data) is skipped rather than treated as a row
missing values, since there is nothing there to be missing.
"""
from __future__ import annotations

import csv
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from flowbio.cli._exit_codes import CliUsageError
from flowbio.cli._files import existing_file
from flowbio.v2.samples import SampleImportSpec, SampleTypeId

RESERVED_COLUMNS = ("accession", "name", "organism", "sample_type")


@dataclass(frozen=True)
class AccessionSheetRow:
    """One data row of an accession sheet."""

    row_number: int
    accession: str
    name: str | None
    organism: str | None
    sample_type: SampleTypeId
    metadata: dict[str, str]

    def __post_init__(self) -> None:
        if not self.accession:
            raise ValueError("accession must not be empty")
        if not self.sample_type:
            raise ValueError("sample_type must not be empty")

    def to_spec(self) -> SampleImportSpec:
        """Build the :class:`~flowbio.v2.samples.SampleImportSpec` for this row."""
        return SampleImportSpec(
            accession=self.accession,
            sample_type=self.sample_type,
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
    :returns: The parsed sheet, with wholly-blank rows skipped, empty cells
        dropped, and surrounding whitespace trimmed (including in header
        names). Values are otherwise passed through unchanged, including
        ``accession``, sent to the server as-entered.
    :raises CliUsageError: If the file is not a readable ``.csv``, has no
        rows, or has a row with no accession or no sample_type.
    """
    if path.suffix.lower() != ".csv":
        raise CliUsageError(
            f"Accession sheet must be a .csv file: {path}. "
            f"Export your spreadsheet to CSV first.",
        )
    existing_file(path)
    rows: list[AccessionSheetRow] = []
    missing_accession: list[int] = []
    missing_sample_type: list[int] = []
    # utf-8-sig transparently strips a leading BOM, which spreadsheet tools
    # (notably Excel's "CSV UTF-8" export) prepend — otherwise the first header
    # parses as "﻿accession" and every row reports a missing accession.
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        # A hand-authored header (unlike upload-batch's template-generated
        # one) routinely has a stray space after a comma; reassigning
        # fieldnames makes every row dict keyed by the trimmed name too.
        headers = [header.strip() for header in reader.fieldnames or []]
        reader.fieldnames = headers
        metadata_columns = [
            header for header in headers if header not in RESERVED_COLUMNS
        ]
        # Row 1 is the first row after the header, matching _sheet.py's
        # convention (and upload-batch's documented "1-based row number").
        for row_number, record in enumerate(reader, start=1):
            if _is_blank_row(record, headers):
                continue
            accession = _cell(record, "accession")
            sample_type = _cell(record, "sample_type")
            if accession is None:
                missing_accession.append(row_number)
            if sample_type is None:
                missing_sample_type.append(row_number)
            if accession is None or sample_type is None:
                continue
            rows.append(_build_row(record, row_number, metadata_columns, accession, sample_type))
    if not rows and not missing_accession and not missing_sample_type:
        raise CliUsageError(f"Accession sheet has no rows: {path}.")
    if missing_accession or missing_sample_type:
        clauses = [
            clause for clause in (
                _missing_value_clause("accession", missing_accession),
                _missing_value_clause("sample_type", missing_sample_type),
            ) if clause is not None
        ]
        raise CliUsageError(f"Accession sheet {'; '.join(clauses)}: {path}.")
    return AccessionSheet(path=path, rows=rows)


def _is_blank_row(record: dict[str, str], headers: Sequence[str]) -> bool:
    return not any((record.get(header) or "").strip() for header in headers)


def _missing_value_clause(column: str, missing: list[int]) -> str | None:
    if not missing:
        return None
    numbers = ", ".join(str(number) for number in missing)
    verb = "has" if len(missing) == 1 else "have"
    return f"data row(s) {numbers} {verb} no {column}"


def _cell(record: dict[str, str], column: str) -> str | None:
    value = (record.get(column) or "").strip()
    return value or None


def _build_row(
    record: dict[str, str],
    row_number: int,
    metadata_columns: list[str],
    accession: str,
    sample_type: str,
) -> AccessionSheetRow:
    metadata = {
        column: value
        for column in metadata_columns
        if (value := _cell(record, column)) is not None
    }
    return AccessionSheetRow(
        row_number=row_number,
        accession=accession,
        name=_cell(record, "name"),
        organism=_cell(record, "organism"),
        sample_type=SampleTypeId(sample_type),
        metadata=metadata,
    )
