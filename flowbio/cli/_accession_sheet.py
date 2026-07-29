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
unique, non-empty name, and every row must have no fewer cells than the
header, and no more unless the extra ones are blank — any of these is a
case the parser can't resolve on the user's behalf, so it's rejected
rather than guessed at. See :func:`parse_accession_sheet`.
"""
from __future__ import annotations

import csv
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from flowbio.cli._exit_codes import CliUsageError
from flowbio.cli._files import existing_file
from flowbio.v2.samples import SampleImportSpec, SampleTypeId

RESERVED_COLUMNS = ("accession", "name", "organism", "sample_type")

# csv.DictReader's row shape: a header's cell, or None if the row was too
# short to reach it; a list[str] of any cells beyond the header, under the
# key None, for a row that was too long.
ParsedRow = Mapping[str | None, str | list[str] | None]


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
        header row, has an unnamed or duplicated column, has no rows, has
        a row with fewer cells than the header or with more cells than the
        header where the overflow isn't blank, or has a row with no
        accession or no sample_type.
    """
    if path.suffix.lower() != ".csv":
        raise CliUsageError(
            f"Accession sheet must be a .csv file: {path}. "
            f"Export your spreadsheet to CSV first.",
        )
    existing_file(path)
    rows: list[AccessionSheetRow] = []
    short_rows: list[int] = []
    overflow_rows: list[int] = []
    missing_accession: list[int] = []
    missing_sample_type: list[int] = []
    # utf-8-sig transparently strips a leading BOM, which spreadsheet tools
    # (notably Excel's "CSV UTF-8" export) prepend — otherwise the first header
    # parses as "﻿accession" and every row reports a missing accession.
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        # A present-but-empty fieldnames list means the first line was
        # blank, not absent (an empty file gives fieldnames=None instead,
        # caught by the "no rows" check below); left unchecked, every data
        # row would overflow a zero-column header instead.
        if reader.fieldnames == []:
            raise CliUsageError(f"Accession sheet has no header row: {path}.")
        headers = [header.strip() for header in reader.fieldnames or []]
        reader.fieldnames = headers
        _check_headers(headers, path)
        metadata_columns = [
            header for header in headers if header not in RESERVED_COLUMNS
        ]
        for row_number, record in enumerate(reader, start=1):
            overflow_has_value = any(cell.strip() for cell in _overflow_cells(record))
            if not overflow_has_value and _is_blank_row(record, headers):
                continue
            # A short row's missing cells could just as easily be trailing
            # optional columns as data landing in the wrong place, so —
            # unlike a too-wide row's blank overflow — it's rejected outright.
            if any(record.get(header) is None for header in headers):
                short_rows.append(row_number)
                continue
            if overflow_has_value:
                overflow_rows.append(row_number)
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
    sheet_is_empty = (
        not rows and not short_rows and not overflow_rows
        and not missing_accession and not missing_sample_type
    )
    if sheet_is_empty:
        raise CliUsageError(f"Accession sheet has no rows: {path}.")
    if short_rows or overflow_rows or missing_accession or missing_sample_type:
        clauses = [
            clause for clause in (
                _row_reason_clause("fewer cells than the header", short_rows),
                _row_reason_clause("more cells than the header", overflow_rows),
                _row_reason_clause("no accession", missing_accession),
                _row_reason_clause("no sample_type", missing_sample_type),
            ) if clause is not None
        ]
        message = f"Accession sheet {'; '.join(clauses)}: {path}."
        remedies: list[str] = []
        if short_rows:
            remedies.append(
                "add the missing trailing comma(s), leaving the cell(s) blank if that "
                "column doesn't apply to this row, or fill in a value",
            )
        if overflow_rows:
            remedies.append(
                "if a value legitimately contains a comma, quote it; otherwise "
                "remove the extra cell(s)",
            )
        message += "".join(f" {remedy[0].upper()}{remedy[1:]}." for remedy in remedies)
        raise CliUsageError(message)
    return AccessionSheet(path=path, rows=rows)


def _check_headers(headers: list[str], path: Path) -> None:
    unnamed = [position for position, header in enumerate(headers, start=1) if not header]
    duplicates = sorted({header for header in headers if header and headers.count(header) > 1})
    if not unnamed and not duplicates:
        return
    clauses: list[str] = []
    remedies: list[str] = []
    if unnamed:
        clauses.append(_unnamed_columns_clause(unnamed))
        remedies.append("remove the trailing comma(s) from the header row, or give the column(s) a name")
    if duplicates:
        clauses.append(_duplicate_columns_clause(duplicates))
        remedies.append("rename the repeated column(s) so each column is unique")
    remedy = ". ".join(f"{r[0].upper()}{r[1:]}" for r in remedies)
    raise CliUsageError(
        f"Accession sheet {'; '.join(clauses)}: {path}. {remedy}.",
    )


def _unnamed_columns_clause(unnamed: list[int]) -> str:
    positions = ", ".join(str(position) for position in unnamed)
    verb = "is" if len(unnamed) == 1 else "are"
    return f"column(s) {positions} {verb} unnamed"


def _duplicate_columns_clause(duplicates: list[str]) -> str:
    names = ", ".join(f"'{name}'" for name in duplicates)
    verb = "is" if len(duplicates) == 1 else "are"
    return f"column name(s) {names} {verb} duplicated"


def _is_blank_row(record: ParsedRow, headers: list[str]) -> bool:
    return not any(_cell(record, header) for header in headers)


def _overflow_cells(record: ParsedRow) -> list[str]:
    overflow = record.get(None)
    return overflow if isinstance(overflow, list) else []


def _row_reason_clause(reason: str, rows: list[int]) -> str | None:
    if not rows:
        return None
    numbers = ", ".join(str(number) for number in rows)
    verb = "has" if len(rows) == 1 else "have"
    return f"data row(s) {numbers} {verb} {reason}"


def _cell(record: ParsedRow, column: str) -> str | None:
    raw = record.get(column)
    value = (raw if isinstance(raw, str) else "").strip()
    return value or None


def _build_row(
    record: ParsedRow,
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
