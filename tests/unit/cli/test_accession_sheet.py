import csv
from pathlib import Path

import pytest

from flowbio.cli._accession_sheet import AccessionSheetRow, parse_accession_sheet
from flowbio.cli._exit_codes import CliUsageError
from flowbio.v2.samples import SampleImportSpec

HEADERS = ["accession", "name", "organism", "sample_type", "cell_type", "source", "source__annotation"]


def _write_sheet(
    directory: Path, *records: dict[str, str], headers: list[str] = HEADERS,
) -> Path:
    path = directory / "sheet.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=headers)
        writer.writeheader()
        writer.writerows(records)
    return path


def _record(**overrides: str) -> dict[str, str]:
    record = {"accession": "ERR1160845", "sample_type": "rna_seq"}
    record.update(overrides)
    return record


class TestParseAccessionSheet:

    def test_accession_is_passed_through_unchanged(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(
            _write_sheet(tmp_path, _record(accession="err1160845")),
        )

        assert sheet.rows[0].accession == "err1160845"

    def test_empty_cells_omitted_from_metadata(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path,
            _record(cell_type="", source="blood"),
        ))

        assert sheet.rows[0].metadata == {"source": "blood"}

    def test_name_and_organism_are_optional(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(
            _write_sheet(tmp_path, _record()),
        )

        assert sheet.rows[0].name is None
        assert sheet.rows[0].organism is None

    def test_name_and_organism_are_parsed_when_present(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path,
            _record(name="liver_r1", organism="Hs"),
        ))

        assert sheet.rows[0].name == "liver_r1"
        assert sheet.rows[0].organism == "Hs"

    def test_sample_type_is_parsed(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path, _record(sample_type="chip_seq"),
        ))

        assert sheet.rows[0].sample_type == "chip_seq"

    def test_utf8_bom_is_stripped_from_first_header(self, tmp_path: Path) -> None:
        path = tmp_path / "sheet.csv"
        with path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=HEADERS)
            writer.writeheader()
            writer.writerow(_record())

        sheet = parse_accession_sheet(path)

        assert sheet.rows[0].accession == "ERR1160845"

    def test_row_numbers_are_one_based(self, tmp_path: Path) -> None:
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path,
            _record(accession="ERR1160845"),
            _record(accession="ERR10677146"),
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

    def test_header_only_sheet_is_usage_error(self, tmp_path: Path) -> None:
        with pytest.raises(CliUsageError, match="no rows"):
            parse_accession_sheet(_write_sheet(tmp_path))

    def test_row_with_blank_accession_is_usage_error(self, tmp_path: Path) -> None:
        with pytest.raises(CliUsageError, match=r"data row\(s\) 2 has no accession"):
            parse_accession_sheet(_write_sheet(
                tmp_path,
                _record(accession="ERR1160845"),
                _record(accession=""),
            ))

    def test_row_with_no_accession_column_is_usage_error(self, tmp_path: Path) -> None:
        path = tmp_path / "sheet.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["run", "name", "sample_type"])
            writer.writeheader()
            writer.writerow({"run": "ERR1160845", "name": "liver_r1", "sample_type": "rna_seq"})

        with pytest.raises(CliUsageError):
            parse_accession_sheet(path)

    def test_usage_error_names_every_row_missing_an_accession(self, tmp_path: Path) -> None:
        with pytest.raises(CliUsageError, match=r"data row\(s\) 1, 3 have no accession"):
            parse_accession_sheet(_write_sheet(
                tmp_path,
                _record(accession=""),
                _record(accession="ERR1"),
                _record(accession=""),
            ))

    def test_row_with_blank_sample_type_is_usage_error(self, tmp_path: Path) -> None:
        with pytest.raises(CliUsageError, match=r"data row\(s\) 1 has no sample_type"):
            parse_accession_sheet(_write_sheet(tmp_path, _record(sample_type="")))

    def test_row_with_no_sample_type_column_is_usage_error(self, tmp_path: Path) -> None:
        path = tmp_path / "sheet.csv"
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["accession", "name"])
            writer.writeheader()
            writer.writerow({"accession": "ERR1160845", "name": "liver_r1"})

        with pytest.raises(CliUsageError):
            parse_accession_sheet(path)

    def test_sheet_broken_in_both_columns_reports_both_in_one_error(
        self, tmp_path: Path,
    ) -> None:
        with pytest.raises(CliUsageError) as excinfo:
            parse_accession_sheet(_write_sheet(
                tmp_path,
                _record(accession=""),
                _record(accession="ERR2", sample_type=""),
            ))

        assert "data row(s) 1 has no accession" in str(excinfo.value)
        assert "data row(s) 2 has no sample_type" in str(excinfo.value)

    def test_trailing_blank_row_is_skipped(self, tmp_path: Path) -> None:
        # A comma-only line, e.g. one a spreadsheet export leaves below the
        # data — not a row with data but no accession, so it isn't an error.
        sheet = parse_accession_sheet(_write_sheet(
            tmp_path,
            _record(accession="ERR1"),
            {},
        ))

        assert [row.accession for row in sheet.rows] == ["ERR1"]

    def test_sheet_of_only_blank_rows_is_usage_error(self, tmp_path: Path) -> None:
        with pytest.raises(CliUsageError, match="no rows"):
            parse_accession_sheet(_write_sheet(tmp_path, {}, {}))


def test_row_rejects_empty_accession_by_construction() -> None:
    with pytest.raises(ValueError, match="accession"):
        AccessionSheetRow(
            row_number=1,
            accession="",
            name=None,
            organism=None,
            sample_type="rna_seq",
            metadata={},
        )


def test_row_rejects_empty_sample_type_by_construction() -> None:
    with pytest.raises(ValueError, match="sample_type"):
        AccessionSheetRow(
            row_number=1,
            accession="ERR1160845",
            name=None,
            organism=None,
            sample_type="",
            metadata={},
        )


class TestAccessionSheetRowToSpec:

    def _row(self, tmp_path: Path, **overrides: str):
        sheet = parse_accession_sheet(_write_sheet(tmp_path, _record(**overrides)))
        return sheet.rows[0]

    def test_uses_the_row_sample_type(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, sample_type="chip_seq")

        spec = row.to_spec()

        assert spec == SampleImportSpec(accession="ERR1160845", sample_type="chip_seq")

    def test_carries_name_organism_and_metadata(self, tmp_path: Path) -> None:
        row = self._row(tmp_path, name="liver_r1", organism="Hs", cell_type="Neuron")

        spec = row.to_spec()

        assert spec == SampleImportSpec(
            accession="ERR1160845",
            sample_type="rna_seq",
            name="liver_r1",
            organism_id="Hs",
            metadata={"cell_type": "Neuron"},
        )

    def test_annotation_suffixed_column_is_forwarded_as_a_plain_metadata_key(
        self, tmp_path: Path,
    ) -> None:
        # Unlike upload-batch, there's no special handling of `<id>__annotation`
        # here — it's just another metadata column, and the server does not
        # recognise it as one (see cli.rst).
        row = self._row(tmp_path, source="blood", source__annotation="left lobe")

        spec = row.to_spec()

        assert spec.metadata == {"source": "blood", "source__annotation": "left lobe"}
