import csv
from pathlib import Path

import pytest

from flowbio.cli._exit_codes import CliUsageError
from flowbio.cli._sheet import parse_sheet, validate_row
from flowbio.v2.samples import MetadataAttribute, SampleTypeId

SAMPLE_TYPE = SampleTypeId("rna_seq")
HEADERS = [
    "name", "reads1", "reads2", "project", "organism",
    "cell_type", "source", "source__annotation",
]


def _attributes() -> list[MetadataAttribute]:
    return [
        MetadataAttribute(
            identifier="cell_type",
            name="Cell Type",
            description="The cell type",
            required=False,
            required_for_sample_types=[SAMPLE_TYPE],
            options=["Neuron", "Fibroblast"],
            allow_annotation=False,
        ),
        MetadataAttribute(
            identifier="source",
            name="Source",
            description="Sample source",
            required=False,
            required_for_sample_types=[],
            options=None,
            allow_annotation=True,
        ),
    ]


def _reads(directory: Path, name: str) -> Path:
    path = directory / name
    path.write_bytes(b"ATCG")
    return path


def _write_sheet(
    directory: Path, *records: dict[str, str], headers: list[str] = HEADERS,
) -> Path:
    path = directory / "sheet.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)
    return path


class TestParseSheet:

    def test_separates_reserved_and_metadata_columns(self, tmp_path: Path) -> None:
        sheet = parse_sheet(
            _write_sheet(tmp_path, {"name": "s1", "reads1": "r1.fq.gz"}),
        )

        assert sheet.metadata_columns == ["cell_type", "source", "source__annotation"]

    def test_reads_paths_resolved_relative_to_sheet_directory(
        self, tmp_path: Path,
    ) -> None:
        sheet = parse_sheet(
            _write_sheet(tmp_path, {"name": "s1", "reads1": "r1.fq.gz"}),
        )

        assert sheet.rows[0].reads1 == tmp_path / "r1.fq.gz"

    def test_absolute_reads_path_used_as_is(self, tmp_path: Path) -> None:
        absolute = tmp_path / "elsewhere" / "r1.fq.gz"

        sheet = parse_sheet(
            _write_sheet(tmp_path, {"name": "s1", "reads1": str(absolute)}),
        )

        assert sheet.rows[0].reads1 == absolute

    def test_empty_cells_omitted_from_metadata(self, tmp_path: Path) -> None:
        sheet = parse_sheet(_write_sheet(
            tmp_path,
            {"name": "s1", "reads1": "r1.fq.gz", "cell_type": "", "source": "blood"},
        ))

        assert sheet.rows[0].metadata == {"source": "blood"}

    def test_utf8_bom_is_stripped_from_first_header(self, tmp_path: Path) -> None:
        path = tmp_path / "sheet.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerow({"name": "s1", "reads1": "r1.fq.gz"})

        sheet = parse_sheet(path)

        assert sheet.metadata_columns == ["cell_type", "source", "source__annotation"]
        assert sheet.rows[0].name == "s1"

    def test_row_numbers_are_one_based(self, tmp_path: Path) -> None:
        sheet = parse_sheet(_write_sheet(
            tmp_path,
            {"name": "s1", "reads1": "r1.fq.gz"},
            {"name": "s2", "reads1": "r2.fq.gz"},
        ))

        assert [row.row_number for row in sheet.rows] == [1, 2]

    def test_non_csv_xlsx_rejected_with_export_message(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "sheet.xlsx"
        xlsx.write_bytes(b"PK")

        with pytest.raises(CliUsageError, match="CSV"):
            parse_sheet(xlsx)

    def test_tsv_sheet_rejected(self, tmp_path: Path) -> None:
        tsv = tmp_path / "sheet.tsv"
        tsv.write_text("name\treads1\n")

        with pytest.raises(CliUsageError, match="CSV"):
            parse_sheet(tsv)


class TestValidateRow:

    def _row(self, directory: Path, **overrides: str):
        _reads(directory, "r1.fq.gz")
        record = {"name": "s1", "reads1": "r1.fq.gz"}
        record.update(overrides)
        sheet = parse_sheet(_write_sheet(directory, record))
        return sheet.rows[0]

    def test_valid_row_has_no_errors(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, cell_type="Neuron")

        assert validate_row(row, _attributes(), SAMPLE_TYPE) == []

    def test_missing_name_reports_error(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, name="", cell_type="Neuron")

        errors = validate_row(row, _attributes(), SAMPLE_TYPE)

        assert any("name" in error for error in errors)

    def test_missing_reads1_reports_error(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, reads1="", cell_type="Neuron")

        errors = validate_row(row, _attributes(), SAMPLE_TYPE)

        assert any("reads1" in error for error in errors)

    def test_missing_reads_file_on_disk_reports_error(self, tmp_path: Path) -> None:
        sheet = parse_sheet(_write_sheet(
            tmp_path,
            {"name": "s1", "reads1": "absent.fq.gz", "cell_type": "Neuron"},
        ))

        errors = validate_row(sheet.rows[0], _attributes(), SAMPLE_TYPE)

        assert any("absent.fq.gz" in error for error in errors)

    def test_name_with_space_reports_error(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, name="bad name", cell_type="Neuron")

        errors = validate_row(row, _attributes(), SAMPLE_TYPE)

        assert any("space" in error.lower() for error in errors)

    def test_value_outside_options_reports_error(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, cell_type="Alien")

        errors = validate_row(row, _attributes(), SAMPLE_TYPE)

        assert any("Alien" in error for error in errors)

    def test_required_for_type_metadata_missing_reports_error(
        self, tmp_path: Path,
    ) -> None:
        row = self._row(tmp_path)

        errors = validate_row(row, _attributes(), SAMPLE_TYPE)

        assert any("cell_type" in error for error in errors)

    def test_annotation_set_without_its_value_reports_error(
        self, tmp_path: Path,
    ) -> None:
        row = self._row(
            tmp_path, cell_type="Neuron", **{"source__annotation": "qPCR"},
        )

        errors = validate_row(row, _attributes(), SAMPLE_TYPE)

        assert any("source__annotation" in error for error in errors)

    def test_annotation_on_non_annotation_attribute_reports_error(
        self, tmp_path: Path,
    ) -> None:
        headers = ["name", "reads1", "cell_type", "cell_type__annotation"]
        _reads(tmp_path, "r1.fq.gz")
        sheet = parse_sheet(_write_sheet(
            tmp_path,
            {
                "name": "s1", "reads1": "r1.fq.gz",
                "cell_type": "Neuron", "cell_type__annotation": "note",
            },
            headers=headers,
        ))

        errors = validate_row(sheet.rows[0], _attributes(), SAMPLE_TYPE)

        assert any(
            "annotation" in error.lower() and "cell_type" in error
            for error in errors
        )

    def test_all_per_row_errors_collected(self, tmp_path: Path) -> None:
        sheet = parse_sheet(_write_sheet(
            tmp_path,
            {"name": "bad name", "reads1": "absent.fq.gz", "cell_type": "Alien"},
        ))

        errors = validate_row(sheet.rows[0], _attributes(), SAMPLE_TYPE)

        assert len(errors) >= 3
