import csv
from pathlib import Path

import pytest

from flowbio.cli._accession_sheet import parse_accession_sheet
from flowbio.cli._exit_codes import CliUsageError

HEADERS = ["accession", "name", "organism", "cell_type", "source", "source__annotation"]


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

    def test_accession_is_passed_through_unchanged(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(
            _write_sheet(tmp_path, {"accession": "err1160845"}),
        )

        assert sheet.rows[0].accession == "err1160845"

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
