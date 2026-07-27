import csv
from pathlib import Path

import pytest

from flowbio.cli._accession_sheet import (
    duplicate_accession_errors,
    parse_accession_sheet,
    validate_accession_row,
)
from flowbio.cli._exit_codes import CliUsageError
from flowbio.v2.samples import MetadataAttribute, SampleTypeId

SAMPLE_TYPE = SampleTypeId("rna_seq")
HEADERS = ["accession", "name", "organism", "cell_type", "source", "source__annotation"]


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


def _write_sheet(
    directory: Path, *records: dict[str, str], headers: list[str] = HEADERS,
) -> Path:
    path = directory / "sheet.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)
    return path


class TestParseAccessionSheet:

    def test_separates_reserved_and_metadata_columns(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(
            _write_sheet(tmp_path, {"accession": "ERR1160845"}),
        )

        assert sheet.metadata_columns == ["cell_type", "source", "source__annotation"]

    def test_accession_is_normalised_to_upper_case(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(
            _write_sheet(tmp_path, {"accession": "err1160845"}),
        )

        assert sheet.rows[0].accession == "ERR1160845"

    def test_empty_cells_omitted_from_metadata(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path,
            {"accession": "ERR1160845", "cell_type": "", "source": "blood"},
        ))

        assert sheet.rows[0].metadata == {"source": "blood"}

    def test_name_and_organism_are_optional(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(
            _write_sheet(tmp_path, {"accession": "ERR1160845"}),
        )

        assert sheet.rows[0].name is None
        assert sheet.rows[0].organism is None

    def test_name_and_organism_are_parsed_when_present(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path,
            {"accession": "ERR1160845", "name": "liver_r1", "organism": "Hs"},
        ))

        assert sheet.rows[0].name == "liver_r1"
        assert sheet.rows[0].organism == "Hs"

    def test_utf8_bom_is_stripped_from_first_header(self, tmp_path: Path) -> None:
        path = tmp_path / "sheet.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerow({"accession": "ERR1160845"})

        sheet = parse_accession_sheet(path)

        assert sheet.metadata_columns == ["cell_type", "source", "source__annotation"]
        assert sheet.rows[0].accession == "ERR1160845"

    def test_row_numbers_are_one_based(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path,
            {"accession": "ERR1160845"},
            {"accession": "ERR10677146"},
        ))

        assert [row.row_number for row in sheet.rows] == [1, 2]

    def test_non_csv_xlsx_rejected_with_export_message(self, tmp_path: Path) -> None:
        xlsx = tmp_path / "sheet.xlsx"
        xlsx.write_bytes(b"PK")

        with pytest.raises(CliUsageError, match="CSV"):
            parse_accession_sheet(xlsx)

    def test_tsv_sheet_rejected(self, tmp_path: Path) -> None:
        tsv = tmp_path / "sheet.tsv"
        tsv.write_text("accession\nERR1160845\n")

        with pytest.raises(CliUsageError, match="CSV"):
            parse_accession_sheet(tsv)

    def test_missing_file_is_usage_error(self, tmp_path: Path) -> None:
        with pytest.raises(CliUsageError):
            parse_accession_sheet(tmp_path / "absent.csv")


class TestValidateAccessionRow:

    def _row(self, directory: Path, **overrides: str):
        record = {"accession": "ERR1160845"}
        record.update(overrides)
        sheet = parse_accession_sheet(_write_sheet(directory, record))
        return sheet.rows[0]

    def test_valid_row_has_no_errors(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, cell_type="Neuron")

        assert validate_accession_row(row, _attributes(), SAMPLE_TYPE) == []

    def test_missing_accession_reports_error(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, accession="", cell_type="Neuron")

        errors = validate_accession_row(row, _attributes(), SAMPLE_TYPE)

        assert any("accession" in error for error in errors)

    def test_unsupported_accession_format_reports_error(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, accession="GSE12345", cell_type="Neuron")

        errors = validate_accession_row(row, _attributes(), SAMPLE_TYPE)

        assert any("GSE12345" in error for error in errors)

    def test_run_and_experiment_accessions_are_supported(self, tmp_path: Path) -> None:
        for accession in ("ERR1160845", "SRR1234567", "DRR7654321", "SRX111", "ERX222", "DRX333"):
            row = self._row(tmp_path, accession=accession, cell_type="Neuron")

            assert validate_accession_row(row, _attributes(), SAMPLE_TYPE) == []

    def test_value_outside_options_reports_error(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, cell_type="Alien")

        errors = validate_accession_row(row, _attributes(), SAMPLE_TYPE)

        assert any("Alien" in error for error in errors)

    def test_required_for_type_metadata_missing_reports_error(
        self, tmp_path: Path,
    ) -> None:
        row = self._row(tmp_path)

        errors = validate_accession_row(row, _attributes(), SAMPLE_TYPE)

        assert any("cell_type" in error for error in errors)

    def test_annotation_set_without_its_value_reports_error(
        self, tmp_path: Path,
    ) -> None:
        row = self._row(
            tmp_path, cell_type="Neuron", **{"source__annotation": "qPCR"},
        )

        errors = validate_accession_row(row, _attributes(), SAMPLE_TYPE)

        assert any("source__annotation" in error for error in errors)

    def test_all_per_row_errors_collected(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path, {"accession": "", "cell_type": "Alien"},
        ))

        errors = validate_accession_row(sheet.rows[0], _attributes(), SAMPLE_TYPE)

        assert len(errors) >= 2


class TestDuplicateAccessionErrors:

    def test_no_errors_when_all_unique(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path, {"accession": "ERR1"}, {"accession": "ERR2"},
        ))

        assert duplicate_accession_errors(sheet.rows) == {}

    def test_repeated_accession_reports_error_on_later_row(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path, {"accession": "ERR1"}, {"accession": "err1"},
        ))

        errors = duplicate_accession_errors(sheet.rows)

        assert 1 not in errors
        assert any("ERR1" in message for message in errors[2])

    def test_blank_accessions_are_not_treated_as_duplicates(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path, {"accession": ""}, {"accession": ""},
        ))

        assert duplicate_accession_errors(sheet.rows) == {}
