"""CSV accession-sheet parsing for ``samples import``.

An accession sheet is a CSV with one row per accession to import: required
``accession`` and ``sample_type`` columns, plus optional ``name``/
``organism`` and per-accession metadata columns. This mirrors ``_sheet.py``'s
reads-based sample sheet, but the reserved columns differ — there is nothing
to upload (no ``reads1``/``reads2``) and the import API has no project field.

Domain rules (accession format, duplicates, sample type, organism, metadata)
are all checked server-side when the sheet is submitted — duplicating that
locally would just be a second, driftable copy of the same rules. What *is*
checked locally is structural: every row must have an accession and a
sample type to mean anything at all, every header column must have a
unique, non-empty name, and every row must have exactly as many cells as
the header — any of these is a case the parser can't resolve on the user's
behalf, so it's rejected rather than guessed at. See :func:`parse_accession_sheet`.
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
    :raises CliUsageError: If the file is not a readable ``.csv``, has an
        unnamed or duplicated column, has no rows, has a row with more
        cells than the header, or has a row with no accession or no
        sample_type.
    """
    if path.suffix.lower() != ".csv":
        raise CliUsageError(
            f"Accession sheet must be a .csv file: {path}. "
            f"Export your spreadsheet to CSV first.",
        )
    existing_file(path)
    rows: list[AccessionSheetRow] = []
    extra_cells: list[int] = []
    missing_accession: list[int] = []
    missing_sample_type: list[int] = []
    # utf-8-sig transparently strips a leading BOM, which spreadsheet tools
    # (notably Excel's "CSV UTF-8" export) prepend — otherwise the first header
    # parses as "﻿accession" and every row reports a missing accession.
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        headers = [header.strip() for header in reader.fieldnames or []]
        reader.fieldnames = headers
        _check_headers(headers, path)
        metadata_columns = [
            header for header in headers if header not in RESERVED_COLUMNS
        ]
        for row_number, record in enumerate(reader, start=1):
            # csv.DictReader stores a row with more cells than the header
            # under the None key; that overflow can't be attributed to any
            # column, so it's rejected rather than silently dropped (or, if
            # every named cell happens to be blank, the whole row silently
            # skipped as though it carried nothing).
            if record.get(None):
                extra_cells.append(row_number)
                continue
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
    if not rows and not extra_cells and not missing_accession and not missing_sample_type:
        raise CliUsageError(f"Accession sheet has no rows: {path}.")
    if extra_cells or missing_accession or missing_sample_type:
        clauses = [
            clause for clause in (
                _row_count_clause("more cells than the header", extra_cells),
                _row_count_clause("no accession", missing_accession),
                _row_count_clause("no sample_type", missing_sample_type),
            ) if clause is not None
        ]
        raise CliUsageError(f"Accession sheet {'; '.join(clauses)}: {path}.")
    return AccessionSheet(path=path, rows=rows)


def _check_headers(headers: Sequence[str], path: Path) -> None:
    unnamed = [position for position, header in enumerate(headers, start=1) if not header]
    duplicates = sorted({header for header in headers if header and headers.count(header) > 1})
    if not unnamed and not duplicates:
        return
    clauses = [
        clause for clause in (
            _unnamed_columns_clause(unnamed),
            _duplicate_columns_clause(duplicates),
        ) if clause is not None
    ]
    raise CliUsageError(
        f"Accession sheet {'; '.join(clauses)}: {path}. Remove the trailing comma(s) "
        f"from the header row, give unnamed columns a name, and rename any repeated "
        f"column so each column is unique.",
    )


def _unnamed_columns_clause(unnamed: list[int]) -> str | None:
    if not unnamed:
        return None
    positions = ", ".join(str(position) for position in unnamed)
    verb = "is" if len(unnamed) == 1 else "are"
    return f"column(s) {positions} {verb} unnamed"


def _duplicate_columns_clause(duplicates: list[str]) -> str | None:
    if not duplicates:
        return None
    names = ", ".join(f"'{name}'" for name in duplicates)
    verb = "is" if len(duplicates) == 1 else "are"
    return f"column name(s) {names} {verb} duplicated"


def _is_blank_row(record: dict[str, str], headers: Sequence[str]) -> bool:
    return not any(_cell(record, header) for header in headers)


def _row_count_clause(reason: str, rows: list[int]) -> str | None:
    if not rows:
        return None
    numbers = ", ".join(str(number) for number in rows)
    verb = "has" if len(rows) == 1 else "have"
    return f"data row(s) {numbers} {verb} {reason}"


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
