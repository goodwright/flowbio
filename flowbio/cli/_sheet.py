"""CSV sample-sheet parsing and pre-flight validation for ``upload-batch``.

A sample sheet is a CSV the user fills in from ``samples batch-template``. Parsing
splits the reserved columns (``name``, ``reads1``, ``reads2``, ``project``,
``organism``) from the metadata-identifier columns, resolves reads paths relative
to the sheet's own directory, and drops empty cells. Validation then collects
*every* problem on each row up front (FR-028) so a batch never half-uploads
before surfacing a fixable mistake.
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from flowbio.cli._exit_codes import CliUsageError
from flowbio.cli._files import existing_file
from flowbio.v2.samples import MetadataAttribute, SampleTypeId

RESERVED_COLUMNS = ("name", "reads1", "reads2", "project", "organism")
ANNOTATION_SUFFIX = "__annotation"
"""Suffix that marks a metadata column as the free-text annotation companion of
``<identifier>``. Shared with ``batch-template`` so the sheet round-trips."""


@dataclass(frozen=True)
class SheetRow:
    """One data row of a sample sheet, with reads paths already resolved.

    ``name``/``reads1`` may be absent (empty cell) — that is reported by
    :func:`validate_row` rather than rejected here, so all errors surface
    together.
    """

    row_number: int
    name: str
    reads1: Path | None
    reads2: Path | None
    project: str | None
    organism: str | None
    metadata: dict[str, str]


@dataclass(frozen=True)
class SampleSheet:
    """A parsed sample sheet."""

    path: Path
    metadata_columns: list[str]
    rows: list[SheetRow]


def parse_sheet(path: Path) -> SampleSheet:
    """Parse a CSV sample sheet into a :class:`SampleSheet`.

    :param path: The sample-sheet file. Must be a ``.csv`` — an ``.xlsx`` or
        ``.tsv`` is a usage error directing the user to export to CSV.
    :returns: The parsed sheet with reserved/metadata columns separated, reads
        paths resolved relative to the sheet's directory, and empty cells dropped.
    :raises CliUsageError: If the file is not a readable ``.csv``.
    """
    if path.suffix.lower() != ".csv":
        raise CliUsageError(
            f"Sample sheet must be a .csv file: {path}. "
            f"Export your spreadsheet to CSV first.",
        )
    existing_file(path)
    with path.open(newline="") as handle:
        reader = csv.DictReader(handle)
        headers = reader.fieldnames or []
        metadata_columns = [
            header for header in headers if header not in RESERVED_COLUMNS
        ]
        rows = [
            _build_row(record, row_number, path.parent, metadata_columns)
            for row_number, record in enumerate(reader, start=1)
        ]
    return SampleSheet(path=path, metadata_columns=metadata_columns, rows=rows)


def validate_row(
    row: SheetRow,
    attributes: list[MetadataAttribute],
    sample_type: SampleTypeId,
) -> list[str]:
    """Return every validation problem on ``row`` (empty when the row is valid).

    :param row: The parsed row to validate.
    :param attributes: The server's metadata attributes, deciding required and
        closed-option columns.
    :param sample_type: The sample type applied to the whole batch; an attribute
        required for it must be present.
    :returns: One human-readable message per problem, collected so the caller can
        report them all at once.
    """
    by_identifier = {attribute.identifier: attribute for attribute in attributes}
    errors: list[str] = []
    if not row.name:
        errors.append("missing required value: name")
    elif " " in row.name:
        errors.append(f"name must not contain spaces: '{row.name}'")
    if row.reads1 is None:
        errors.append("missing required value: reads1")
    for label, reads in (("reads1", row.reads1), ("reads2", row.reads2)):
        if reads is not None and not reads.is_file():
            errors.append(f"{label} file not found: {reads}")
    errors.extend(_metadata_errors(row, by_identifier, attributes, sample_type))
    return errors


def _build_row(
    record: dict[str, str],
    row_number: int,
    base_dir: Path,
    metadata_columns: list[str],
) -> SheetRow:
    def cell(column: str) -> str | None:
        value = (record.get(column) or "").strip()
        return value or None

    metadata = {
        column: value
        for column in metadata_columns
        if (value := (record.get(column) or "").strip())
    }
    return SheetRow(
        row_number=row_number,
        name=cell("name") or "",
        reads1=_resolve(cell("reads1"), base_dir),
        reads2=_resolve(cell("reads2"), base_dir),
        project=cell("project"),
        organism=cell("organism"),
        metadata=metadata,
    )


def _resolve(value: str | None, base_dir: Path) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else base_dir / path


def _metadata_errors(
    row: SheetRow,
    by_identifier: dict[str, MetadataAttribute],
    attributes: list[MetadataAttribute],
    sample_type: SampleTypeId,
) -> list[str]:
    errors: list[str] = []
    for attribute in attributes:
        required = (
            attribute.required or sample_type in attribute.required_for_sample_types
        )
        if required and not row.metadata.get(attribute.identifier):
            errors.append(f"missing required metadata: {attribute.identifier}")
    for key, value in row.metadata.items():
        if key.endswith(ANNOTATION_SUFFIX):
            continue
        attribute = by_identifier.get(key)
        if attribute is not None and attribute.options is not None and value not in attribute.options:
            errors.append(
                f"value '{value}' for {key} is not one of: "
                f"{', '.join(attribute.options)}",
            )
    for key in row.metadata:
        if not key.endswith(ANNOTATION_SUFFIX):
            continue
        base = key[: -len(ANNOTATION_SUFFIX)]
        if not row.metadata.get(base):
            errors.append(f"{key} set without a value for {base}")
            continue
        attribute = by_identifier.get(base)
        if attribute is not None and not attribute.allow_annotation:
            errors.append(f"{base} does not allow an annotation")
    return errors
