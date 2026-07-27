import csv
import json
from http import HTTPStatus
from pathlib import Path

import httpx
import respx

from tests.unit.cli.conftest import DEFAULT_BASE_URL
from tests.unit.v2.conftest import parse_multipart

SAMPLE_UPLOAD_URL = f"{DEFAULT_BASE_URL}/upload/sample"
ANNOTATION_TEMPLATE_URL = f"{DEFAULT_BASE_URL}/annotation"
ANNOTATION_UPLOAD_URL = f"{DEFAULT_BASE_URL}/upload/annotation"
MULTIPLEXED_UPLOAD_URL = f"{DEFAULT_BASE_URL}/upload/multiplexed"
SAMPLE_IMPORTS_URL = f"{DEFAULT_BASE_URL}/v2/sample-imports"
TOKEN = "test.token"


def _reads(tmp_path: Path, name: str) -> Path:
    path = tmp_path / name
    path.write_bytes(b"ATCGATCG")
    return path


def _mock_single_upload(sample_id: str = "samp_1") -> respx.Route:
    return respx.post(SAMPLE_UPLOAD_URL).mock(
        return_value=httpx.Response(
            HTTPStatus.OK, json={"sample_id": sample_id, "data_id": "data_1"},
        ),
    )


class TestSamplesUpload:

    @respx.mock
    def test_single_ended_create_prints_identifier(
        self, run_cli, tmp_path: Path,
    ) -> None:
        sample_id = "samp_xyz"
        _mock_single_upload(sample_id)

        result = run_cli(
            "--token", TOKEN, "samples", "upload",
            "--name", "s1", "--sample-type", "rna_seq",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--no-progress",
        )

        assert result.exit_code == 0
        assert sample_id in result.stdout

    @respx.mock
    def test_json_emits_single_document_on_stdout_only(
        self, run_cli, tmp_path: Path,
    ) -> None:
        sample_id = "samp_xyz"
        _mock_single_upload(sample_id)

        result = run_cli(
            "samples", "upload", "--name", "s1", "--sample-type", "rna_seq",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--token", TOKEN, "--no-progress", "--json",
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"id": sample_id}
        assert result.stdout.count("\n") == 1

    @respx.mock
    def test_reads2_makes_it_paired_end(self, run_cli, tmp_path: Path) -> None:
        route = respx.post(SAMPLE_UPLOAD_URL)
        route.side_effect = [
            httpx.Response(HTTPStatus.OK, json={"sample_id": None, "data_id": "d1"}),
            httpx.Response(HTTPStatus.OK, json={"sample_id": "s1", "data_id": "d2"}),
        ]

        result = run_cli(
            "samples", "upload", "--name", "s1", "--sample-type", "rna_seq",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--reads2", str(_reads(tmp_path, "r2.fq.gz")),
            "--token", TOKEN, "--no-progress",
        )

        assert result.exit_code == 0
        assert route.call_count == 2

    @respx.mock
    def test_repeated_metadata_pairs_sent_as_fields(
        self, run_cli, tmp_path: Path,
    ) -> None:
        equation = "a=b+c"
        route = _mock_single_upload()

        run_cli(
            "samples", "upload", "--name", "s1", "--sample-type", "rna_seq",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--metadata", "strandedness=reverse",
            "--metadata", f"formula={equation}",
            "--token", TOKEN, "--no-progress",
        )

        fields, _ = parse_multipart(route.calls[0].request)
        assert fields["strandedness"] == "reverse"
        assert fields["formula"] == equation

    @respx.mock
    def test_metadata_json_object_sent_as_fields(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = _mock_single_upload()

        run_cli(
            "samples", "upload", "--name", "s1", "--sample-type", "rna_seq",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--metadata-json", json.dumps({"strandedness": "forward", "depth": "30"}),
            "--token", TOKEN, "--no-progress",
        )

        fields, _ = parse_multipart(route.calls[0].request)
        assert fields["strandedness"] == "forward"
        assert fields["depth"] == "30"

    @respx.mock
    def test_conflicting_metadata_key_is_usage_error_before_upload(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = _mock_single_upload()

        result = run_cli(
            "samples", "upload", "--name", "s1", "--sample-type", "rna_seq",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--metadata", "strandedness=reverse",
            "--metadata-json", json.dumps({"strandedness": "forward"}),
            "--token", TOKEN, "--no-progress",
        )

        assert result.exit_code == 2
        assert route.call_count == 0
        assert "strandedness" in result.stderr

    @respx.mock
    def test_annotation_companion_passed_through(
        self, run_cli, tmp_path: Path,
    ) -> None:
        annotation = "measured by qPCR"
        route = _mock_single_upload()

        run_cli(
            "samples", "upload", "--name", "s1", "--sample-type", "rna_seq",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--metadata", "cell_type=Neuron",
            "--metadata", f"cell_type__annotation={annotation}",
            "--token", TOKEN, "--no-progress",
        )

        fields, _ = parse_multipart(route.calls[0].request)
        assert fields["cell_type"] == "Neuron"
        assert fields["cell_type__annotation"] == annotation

    @respx.mock
    def test_metadata_json_non_string_value_is_usage_error_before_upload(
        self, run_cli, tmp_path: Path,
    ) -> None:
        offending_key = "paired"
        route = _mock_single_upload()

        result = run_cli(
            "samples", "upload", "--name", "s1", "--sample-type", "rna_seq",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--metadata-json", json.dumps({offending_key: True}),
            "--token", TOKEN, "--no-progress",
        )

        assert result.exit_code == 2
        assert route.call_count == 0
        assert offending_key in result.stderr

    @respx.mock
    def test_empty_metadata_key_is_usage_error_before_upload(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = _mock_single_upload()

        result = run_cli(
            "samples", "upload", "--name", "s1", "--sample-type", "rna_seq",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--metadata", "=orphan",
            "--token", TOKEN, "--no-progress",
        )

        assert result.exit_code == 2
        assert route.call_count == 0

    def test_name_help_does_not_promise_cli_space_validation(self, run_cli) -> None:
        result = run_cli("samples", "upload", "--help")

        assert result.exit_code == 0
        assert "must not contain spaces" not in result.stdout


def _mock_annotation_template(
    sample_type: str, content: bytes = b"PK\x03\x04xlsx",
) -> respx.Route:
    return respx.get(f"{ANNOTATION_TEMPLATE_URL}/{sample_type}").mock(
        return_value=httpx.Response(HTTPStatus.OK, content=content),
    )


class TestSamplesAnnotationTemplate:

    @respx.mock
    def test_writes_xlsx_bytes_to_output_with_confirmation(
        self, run_cli, tmp_path: Path,
    ) -> None:
        sample_type = "rna_seq"
        workbook = b"PK\x03\x04 fake xlsx workbook bytes"
        _mock_annotation_template(sample_type, workbook)
        output_path = tmp_path / "sheet.xlsx"

        result = run_cli(
            "--token", TOKEN, "samples", "annotation-template",
            "--sample-type", sample_type, "-o", str(output_path),
        )

        assert result.exit_code == 0
        assert output_path.read_bytes() == workbook
        assert str(output_path) in result.stderr
        assert sample_type in result.stderr
        assert result.stdout == ""

    @respx.mock
    def test_sample_type_defaults_to_generic(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = _mock_annotation_template("generic")
        output_path = tmp_path / "sheet.xlsx"

        result = run_cli(
            "--token", TOKEN, "samples", "annotation-template",
            "-o", str(output_path),
        )

        assert result.exit_code == 0
        assert route.called

    @respx.mock
    def test_missing_output_is_usage_error(self, run_cli) -> None:
        route = _mock_annotation_template("generic")

        result = run_cli("--token", TOKEN, "samples", "annotation-template")

        assert result.exit_code == 2
        assert route.call_count == 0

    @respx.mock
    def test_unwritable_output_path_is_usage_error(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_annotation_template("generic")
        output_path = tmp_path / "does-not-exist" / "sheet.xlsx"

        result = run_cli(
            "--token", TOKEN, "samples", "annotation-template",
            "-o", str(output_path),
        )

        assert result.exit_code == 2

    @respx.mock
    def test_json_emits_single_document_without_bytes(
        self, run_cli, tmp_path: Path,
    ) -> None:
        sample_type = "rna_seq"
        _mock_annotation_template(sample_type)
        output_path = tmp_path / "sheet.xlsx"

        result = run_cli(
            "--token", TOKEN, "samples", "annotation-template",
            "--sample-type", sample_type, "-o", str(output_path), "--json",
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "output": str(output_path), "sample_type": sample_type,
        }
        assert result.stdout.count("\n") == 1

    @respx.mock
    def test_unknown_sample_type_is_not_found(
        self, run_cli, tmp_path: Path,
    ) -> None:
        respx.get(f"{ANNOTATION_TEMPLATE_URL}/nope").mock(
            return_value=httpx.Response(
                HTTPStatus.NOT_FOUND, json={"error": "no such sample type"},
            ),
        )
        output_path = tmp_path / "sheet.xlsx"

        result = run_cli(
            "--token", TOKEN, "samples", "annotation-template",
            "--sample-type", "nope", "-o", str(output_path),
        )

        assert result.exit_code == 4


def _annotation(tmp_path: Path) -> Path:
    path = tmp_path / "annotation.xlsx"
    path.write_bytes(b"PK\x03\x04annotation")
    return path


def _mock_annotation_accepted(annotation_id: str = "ann_1") -> respx.Route:
    return respx.post(ANNOTATION_UPLOAD_URL).mock(
        return_value=httpx.Response(HTTPStatus.OK, json={"id": annotation_id}),
    )


def _mock_multiplexed(data_id: str = "mux_1") -> respx.Route:
    return respx.post(MULTIPLEXED_UPLOAD_URL).mock(
        return_value=httpx.Response(HTTPStatus.OK, json={"id": data_id}),
    )


class TestSamplesUploadMultiplexed:

    @respx.mock
    def test_reports_data_annotation_ids_and_warnings(
        self, run_cli, tmp_path: Path,
    ) -> None:
        annotation_id = "ann_xyz"
        data_id = "mux_xyz"
        _mock_annotation_accepted(annotation_id)
        _mock_multiplexed(data_id)

        result = run_cli(
            "--token", TOKEN, "samples", "upload-multiplexed",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--annotation", str(_annotation(tmp_path)),
            "--no-progress", "--json",
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {
            "data_ids": [data_id], "annotation_id": annotation_id, "warnings": [],
        }

    @respx.mock
    def test_reads2_makes_it_paired_end(self, run_cli, tmp_path: Path) -> None:
        _mock_annotation_accepted()
        multiplexed = respx.post(MULTIPLEXED_UPLOAD_URL)
        multiplexed.side_effect = [
            httpx.Response(HTTPStatus.OK, json={"id": "mux_1"}),
            httpx.Response(HTTPStatus.OK, json={"id": "mux_2"}),
        ]

        result = run_cli(
            "--token", TOKEN, "samples", "upload-multiplexed",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--reads2", str(_reads(tmp_path, "r2.fq.gz")),
            "--annotation", str(_annotation(tmp_path)),
            "--no-progress",
        )

        assert result.exit_code == 0
        assert multiplexed.call_count == 2

    @respx.mock
    def test_warnings_reported_but_upload_proceeds_by_default(
        self, run_cli, tmp_path: Path,
    ) -> None:
        warnings = [{"row": 1, "message": "Unknown barcode"}]
        annotation = respx.post(ANNOTATION_UPLOAD_URL)
        annotation.side_effect = [
            httpx.Response(HTTPStatus.BAD_REQUEST, json={"warnings": warnings}),
            httpx.Response(HTTPStatus.OK, json={"id": "ann_1"}),
        ]
        _mock_multiplexed()

        result = run_cli(
            "--token", TOKEN, "samples", "upload-multiplexed",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--annotation", str(_annotation(tmp_path)),
            "--no-progress", "--json",
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout)["warnings"] == warnings

    @respx.mock
    def test_warnings_rendered_readably_in_human_mode(
        self, run_cli, tmp_path: Path,
    ) -> None:
        message = "Unknown barcode"
        annotation = respx.post(ANNOTATION_UPLOAD_URL)
        annotation.side_effect = [
            httpx.Response(
                HTTPStatus.BAD_REQUEST,
                json={"warnings": [{"row": 1, "message": message}]},
            ),
            httpx.Response(HTTPStatus.OK, json={"id": "ann_1"}),
        ]
        _mock_multiplexed()

        result = run_cli(
            "--token", TOKEN, "samples", "upload-multiplexed",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--annotation", str(_annotation(tmp_path)),
            "--no-progress",
        )

        assert result.exit_code == 0
        assert f"row 1: {message}" in result.stderr
        assert "{'row'" not in result.stderr

    @respx.mock
    def test_reject_warnings_rejects_upload(
        self, run_cli, tmp_path: Path,
    ) -> None:
        respx.post(ANNOTATION_UPLOAD_URL).mock(
            return_value=httpx.Response(
                HTTPStatus.BAD_REQUEST,
                json={"warnings": [{"row": 1, "message": "Unknown barcode"}]},
            ),
        )
        multiplexed = _mock_multiplexed()

        result = run_cli(
            "--token", TOKEN, "samples", "upload-multiplexed",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--annotation", str(_annotation(tmp_path)),
            "--reject-warnings", "--no-progress",
        )

        assert result.exit_code == 5
        assert multiplexed.call_count == 0

    @respx.mock
    def test_annotation_validation_failure_rejects_upload(
        self, run_cli, tmp_path: Path,
    ) -> None:
        detail = "Invalid scientist"
        respx.post(ANNOTATION_UPLOAD_URL).mock(
            return_value=httpx.Response(
                HTTPStatus.BAD_REQUEST,
                json={"validation": [{"row": 1, "message": detail}]},
            ),
        )
        multiplexed = _mock_multiplexed()

        result = run_cli(
            "--token", TOKEN, "samples", "upload-multiplexed",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--annotation", str(_annotation(tmp_path)),
            "--no-progress",
        )

        assert result.exit_code == 5
        assert multiplexed.call_count == 0
        assert f"row 1: {detail}" in result.stderr

    @respx.mock
    def test_annotation_validation_errors_in_json_error_document(
        self, run_cli, tmp_path: Path,
    ) -> None:
        errors = [{"row": 1, "message": "Invalid scientist"}]
        respx.post(ANNOTATION_UPLOAD_URL).mock(
            return_value=httpx.Response(
                HTTPStatus.BAD_REQUEST, json={"validation": errors},
            ),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "upload-multiplexed",
            "--reads1", str(_reads(tmp_path, "r1.fq.gz")),
            "--annotation", str(_annotation(tmp_path)),
            "--no-progress", "--json",
        )

        assert result.exit_code == 5
        assert result.stdout == ""
        assert json.loads(result.stderr)["errors"] == errors


METADATA_URL = f"{DEFAULT_BASE_URL}/samples/metadata"
RESERVED_HEADER = "name,reads1,reads2,project,organism"


def _mock_metadata() -> None:
    respx.get(f"{DEFAULT_BASE_URL}/samples/types").mock(
        return_value=httpx.Response(HTTPStatus.OK, json=[
            {
                "identifier": "rna_seq",
                "name": "RNA-Seq",
                "description": "RNA sequencing.",
            },
        ]),
    )
    respx.get(METADATA_URL).mock(
        return_value=httpx.Response(HTTPStatus.OK, json=[
            {
                "identifier": "cell_type",
                "name": "Cell Type",
                "description": "The cell type",
                "required": False,
                "required_for_public": False,
                "all_sample_types": False,
                "allow_user_terms": False,
                "regex_validator": None,
                "has_options": True,
                "allow_annotation": False,
                "sample_type_links": [
                    {"sample_type_identifier": "rna_seq", "required": True},
                ],
            },
            {
                "identifier": "source",
                "name": "Source",
                "description": "Sample source",
                "required": False,
                "required_for_public": False,
                "all_sample_types": True,
                "allow_user_terms": False,
                "regex_validator": None,
                "has_options": False,
                "allow_annotation": True,
                "sample_type_links": [],
            },
        ]),
    )
    respx.get(f"{METADATA_URL}/cell_type/options").mock(
        return_value=httpx.Response(
            HTTPStatus.OK,
            json={"options": [{"value": "Neuron"}, {"value": "Fibroblast"}]},
        ),
    )


class TestSamplesBatchTemplate:

    @respx.mock
    def test_csv_header_orders_reserved_then_metadata_with_annotation_companion(
        self, run_cli,
    ) -> None:
        _mock_metadata()

        result = run_cli(
            "samples", "batch-template", "--sample-type", "rna_seq",
            "--token", TOKEN,
        )

        assert result.exit_code == 0
        assert result.stdout.strip() == (
            f"{RESERVED_HEADER},cell_type,source,source__annotation"
        )
        assert "sample_type" not in result.stdout

    @respx.mock
    def test_summary_of_required_columns_on_stderr_without_json(
        self, run_cli,
    ) -> None:
        _mock_metadata()

        result = run_cli(
            "samples", "batch-template", "--sample-type", "rna_seq",
            "--token", TOKEN,
        )

        assert "cell_type" in result.stderr
        assert "source" in result.stderr

    @respx.mock
    def test_output_flag_writes_csv_to_file(self, run_cli, tmp_path: Path) -> None:
        _mock_metadata()
        destination = tmp_path / "template.csv"

        result = run_cli(
            "samples", "batch-template", "--sample-type", "rna_seq",
            "-o", str(destination), "--token", TOKEN,
        )

        assert result.exit_code == 0
        assert destination.read_text().splitlines()[0] == (
            f"{RESERVED_HEADER},cell_type,source,source__annotation"
        )
        assert "cell_type" not in result.stdout

    @respx.mock
    def test_json_emits_column_descriptors_and_no_csv(self, run_cli) -> None:
        _mock_metadata()

        result = run_cli(
            "samples", "batch-template", "--sample-type", "rna_seq",
            "--json", "--token", TOKEN,
        )

        assert result.exit_code == 0
        descriptors = json.loads(result.stdout)
        assert result.stdout.count("\n") == 1
        by_name = {column["name"]: column for column in descriptors}
        assert by_name["name"]["kind"] == "reserved"
        assert by_name["name"]["required"] is True
        assert by_name["cell_type"]["kind"] == "metadata"
        assert by_name["cell_type"]["required"] is True
        assert by_name["cell_type"]["options"] == ["Neuron", "Fibroblast"]
        assert by_name["source__annotation"]["kind"] == "annotation"
        assert by_name["source"]["required"] is False
        assert "sample_type" not in by_name

    @respx.mock
    def test_json_with_output_writes_csv_file_and_emits_descriptors(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        destination = tmp_path / "template.csv"

        result = run_cli(
            "samples", "batch-template", "--sample-type", "rna_seq",
            "--json", "-o", str(destination), "--token", TOKEN,
        )

        assert result.exit_code == 0
        assert destination.read_text().splitlines()[0] == (
            f"{RESERVED_HEADER},cell_type,source,source__annotation"
        )
        descriptors = json.loads(result.stdout)
        assert [column["name"] for column in descriptors][:5] == [
            "name", "reads1", "reads2", "project", "organism",
        ]

    @respx.mock
    def test_unwritable_output_path_is_usage_error(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        destination = tmp_path / "does-not-exist" / "template.csv"

        result = run_cli(
            "samples", "batch-template", "--sample-type", "rna_seq",
            "-o", str(destination), "--token", TOKEN,
        )

        assert result.exit_code == 2
        assert "Traceback" not in result.stderr

    @respx.mock
    def test_unknown_sample_type_is_usage_error_listing_types(self, run_cli) -> None:
        _mock_metadata()

        result = run_cli(
            "samples", "batch-template", "--sample-type", "bogus",
            "--token", TOKEN,
        )

        assert result.exit_code == 2
        assert "bogus" in result.stderr
        assert "rna_seq" in result.stderr
        assert result.stdout == ""

    def test_missing_sample_type_is_usage_error(self, run_cli) -> None:
        result = run_cli("samples", "batch-template", "--token", TOKEN)

        assert result.exit_code == 2


BATCH_HEADERS = [
    "name", "reads1", "reads2", "project", "organism",
    "cell_type", "source", "source__annotation",
]


def _write_batch_sheet(directory: Path, *records: dict[str, str]) -> Path:
    path = directory / "sheet.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=BATCH_HEADERS)
        writer.writeheader()
        writer.writerows(records)
    return path


class TestSamplesUploadBatch:

    @respx.mock
    def test_uploads_all_rows_with_uniform_sample_type(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        upload = respx.post(SAMPLE_UPLOAD_URL)
        upload.side_effect = [
            httpx.Response(HTTPStatus.OK, json={"sample_id": "samp_1", "data_id": "d1"}),
            httpx.Response(HTTPStatus.OK, json={"sample_id": "samp_2", "data_id": "d2"}),
        ]
        _reads(tmp_path, "r1.fq.gz")
        _reads(tmp_path, "r2.fq.gz")
        sheet = _write_batch_sheet(
            tmp_path,
            {"name": "s1", "reads1": "r1.fq.gz", "cell_type": "Neuron"},
            {"name": "s2", "reads1": "r2.fq.gz", "cell_type": "Fibroblast"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(sheet), "--sample-type", "rna_seq", "--no-progress",
        )

        assert result.exit_code == 0
        assert upload.call_count == 2
        for call in upload.calls:
            fields, _ = parse_multipart(call.request)
            assert fields["sample_type"] == "rna_seq"

    @respx.mock
    def test_reads_resolved_relative_to_sheet_directory(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        _mock_single_upload()
        sheet_dir = tmp_path / "run"
        sheet_dir.mkdir()
        _reads(sheet_dir, "r1.fq.gz")
        sheet = _write_batch_sheet(
            sheet_dir, {"name": "s1", "reads1": "r1.fq.gz", "cell_type": "Neuron"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(sheet), "--sample-type", "rna_seq", "--no-progress",
        )

        assert result.exit_code == 0

    @respx.mock
    def test_invalid_row_aborts_and_uploads_nothing(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        upload = _mock_single_upload()
        _reads(tmp_path, "r1.fq.gz")
        sheet = _write_batch_sheet(
            tmp_path,
            {"name": "s1", "reads1": "r1.fq.gz", "cell_type": "Neuron"},
            {"name": "s2", "reads1": "missing.fq.gz", "cell_type": "Neuron"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(sheet), "--sample-type", "rna_seq", "--no-progress",
        )

        assert result.exit_code == 2
        assert upload.call_count == 0
        assert "Row 2" in result.stderr
        assert "s2" in result.stderr

    @respx.mock
    def test_invalid_row_abort_emits_json_error_on_stderr_only(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        upload = _mock_single_upload()
        _reads(tmp_path, "r1.fq.gz")
        sheet = _write_batch_sheet(
            tmp_path,
            {"name": "s1", "reads1": "r1.fq.gz", "cell_type": "Neuron"},
            {"name": "s2", "reads1": "missing.fq.gz", "cell_type": "Neuron"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
            "--no-progress", "--json",
        )

        assert result.exit_code == 2
        assert upload.call_count == 0
        assert result.stdout == ""
        assert any(
            "s2" in detail for detail in json.loads(result.stderr)["errors"]
        )

    @respx.mock
    def test_skip_invalid_uploads_valid_rows(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        upload = _mock_single_upload("samp_ok")
        _reads(tmp_path, "r1.fq.gz")
        sheet = _write_batch_sheet(
            tmp_path,
            {"name": "s1", "reads1": "r1.fq.gz", "cell_type": "Neuron"},
            {"name": "s2", "reads1": "missing.fq.gz", "cell_type": "Neuron"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
            "--skip-invalid", "--no-progress",
        )

        assert result.exit_code == 0
        assert upload.call_count == 1
        assert "s2" in result.stderr

    @respx.mock
    def test_default_continues_past_upload_failure(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        upload = respx.post(SAMPLE_UPLOAD_URL)
        upload.side_effect = [
            httpx.Response(HTTPStatus.BAD_REQUEST, json={"error": "bad"}),
            httpx.Response(HTTPStatus.OK, json={"sample_id": "samp_2", "data_id": "d2"}),
        ]
        _reads(tmp_path, "r1.fq.gz")
        _reads(tmp_path, "r2.fq.gz")
        sheet = _write_batch_sheet(
            tmp_path,
            {"name": "s1", "reads1": "r1.fq.gz", "cell_type": "Neuron"},
            {"name": "s2", "reads1": "r2.fq.gz", "cell_type": "Neuron"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(sheet), "--sample-type", "rna_seq", "--no-progress",
        )

        assert result.exit_code == 1
        assert upload.call_count == 2

    @respx.mock
    def test_stop_on_error_aborts_after_first_failure(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        upload = respx.post(SAMPLE_UPLOAD_URL)
        upload.side_effect = [
            httpx.Response(HTTPStatus.OK, json={"sample_id": "samp_1", "data_id": "d1"}),
            httpx.Response(HTTPStatus.BAD_REQUEST, json={"error": "bad"}),
            httpx.Response(HTTPStatus.OK, json={"sample_id": "samp_3", "data_id": "d3"}),
        ]
        for name in ("r1.fq.gz", "r2.fq.gz", "r3.fq.gz"):
            _reads(tmp_path, name)
        sheet = _write_batch_sheet(
            tmp_path,
            {"name": "s1", "reads1": "r1.fq.gz", "cell_type": "Neuron"},
            {"name": "s2", "reads1": "r2.fq.gz", "cell_type": "Neuron"},
            {"name": "s3", "reads1": "r3.fq.gz", "cell_type": "Neuron"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
            "--stop-on-error", "--no-progress", "--json",
        )

        assert result.exit_code == 1
        assert upload.call_count == 2
        assert [row["name"] for row in json.loads(result.stdout)["uploaded"]] == ["s1"]

    @respx.mock
    def test_json_document_reports_outcomes_and_counts(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        upload = respx.post(SAMPLE_UPLOAD_URL)
        upload.side_effect = [
            httpx.Response(HTTPStatus.OK, json={"sample_id": "samp_1", "data_id": "d1"}),
            httpx.Response(HTTPStatus.BAD_REQUEST, json={"error": "bad"}),
        ]
        _reads(tmp_path, "r1.fq.gz")
        _reads(tmp_path, "r2.fq.gz")
        sheet = _write_batch_sheet(
            tmp_path,
            {"name": "s1", "reads1": "r1.fq.gz", "cell_type": "Neuron"},
            {"name": "s2", "reads1": "r2.fq.gz", "cell_type": "Neuron"},
            {"name": "s3", "reads1": "missing.fq.gz", "cell_type": "Neuron"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
            "--skip-invalid", "--no-progress", "--json",
        )

        assert result.exit_code == 1
        document = json.loads(result.stdout)
        assert result.stdout.count("\n") == 1
        assert document["counts"] == {"uploaded": 1, "failed": 1, "skipped": 1}
        assert document["uploaded"][0]["sample_id"] == "samp_1"
        assert document["failed"][0]["name"] == "s2"
        assert document["skipped"][0]["name"] == "s3"

    @respx.mock
    def test_sample_type_is_not_pre_validated_against_server(
        self, run_cli, tmp_path: Path,
    ) -> None:
        _mock_metadata()
        upload = _mock_single_upload("samp_unknown")
        _reads(tmp_path, "r1.fq.gz")
        sheet = _write_batch_sheet(tmp_path, {"name": "s1", "reads1": "r1.fq.gz"})

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(sheet), "--sample-type", "absent_from_types",
            "--no-progress",
        )

        assert result.exit_code == 0
        assert upload.call_count == 1

    @respx.mock
    def test_non_csv_sheet_is_usage_error(self, run_cli, tmp_path: Path) -> None:
        _mock_metadata()
        upload = _mock_single_upload()
        xlsx = tmp_path / "sheet.xlsx"
        xlsx.write_bytes(b"PK\x03\x04")

        result = run_cli(
            "--token", TOKEN, "samples", "upload-batch",
            "--sheet", str(xlsx), "--sample-type", "rna_seq", "--no-progress",
        )

        assert result.exit_code == 2
        assert upload.call_count == 0
        assert "CSV" in result.stderr


IMPORT_HEADERS = ["accession", "name", "organism", "sample_type", "cell_type", "source", "source__annotation"]


def _write_import_sheet(directory: Path, *records: dict[str, str]) -> Path:
    path = directory / "accessions.csv"
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=IMPORT_HEADERS)
        writer.writeheader()
        writer.writerows(records)
    return path


def _job_json(
    job_id: int,
    status: str,
    accessions: list[str],
    sample_ids: list[int] | None = None,
    error: str | None = None,
    execution_id: int | None = 7,
) -> dict:
    return {
        "id": job_id,
        "status": status,
        "created": 1700000000,
        "started": 1700000001 if status != "RUNNING" else None,
        "finished": 1700000002 if status in ("COMPLETED", "FAILED") else None,
        "accessions": accessions,
        "sample_ids": sample_ids or [],
        "execution_id": execution_id,
        "error": error,
    }


class TestSamplesImport:

    @respx.mock
    def test_kicks_off_job_and_reports_id_without_waiting(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL).mock(
            return_value=httpx.Response(HTTPStatus.CREATED, json=_job_json(
                42, "RUNNING", ["ERR1", "ERR2"],
            )),
        )
        sheet = _write_import_sheet(
            tmp_path,
            {"accession": "ERR1", "cell_type": "Neuron"},
            {"accession": "ERR2", "cell_type": "Fibroblast"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
        )

        assert result.exit_code == 0
        assert route.call_count == 1
        assert "42" in result.stdout
        assert "import-status" in result.stdout

    @respx.mock
    def test_json_document_reports_job_fields(
        self, run_cli, tmp_path: Path,
    ) -> None:
        respx.post(SAMPLE_IMPORTS_URL).mock(
            return_value=httpx.Response(HTTPStatus.CREATED, json=_job_json(
                42, "RUNNING", ["ERR1"],
            )),
        )
        sheet = _write_import_sheet(tmp_path, {"accession": "ERR1", "cell_type": "Neuron"})

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "rna_seq", "--json",
        )

        assert result.exit_code == 0
        document = json.loads(result.stdout)
        assert result.stdout.count("\n") == 1
        assert document == {
            "id": 42,
            "status": "RUNNING",
            "created": "2023-11-14T22:13:20Z",
            "started": None,
            "finished": None,
            "accessions": ["ERR1"],
            "sample_ids": [],
            "execution_id": 7,
            "error": None,
        }

    @respx.mock
    def test_sends_every_row_without_local_validation(
        self, run_cli, tmp_path: Path,
    ) -> None:
        # No metadata/sample-type endpoints are mocked: if the command called
        # client.samples.get_metadata_attributes() or otherwise validated
        # locally, respx would fail the test for an unmocked request.
        route = respx.post(SAMPLE_IMPORTS_URL).mock(
            return_value=httpx.Response(HTTPStatus.CREATED, json=_job_json(
                1, "RUNNING", ["not-an-accession", "ERR1", "ERR1"],
            )),
        )
        sheet = _write_import_sheet(
            tmp_path,
            {"accession": "not-an-accession"},
            {"accession": "ERR1"},
            {"accession": "ERR1"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
        )

        assert result.exit_code == 0
        payload = json.loads(route.calls[0].request.content)
        assert [entry["accession"] for entry in payload["imports"]] == [
            "not-an-accession", "ERR1", "ERR1",
        ]

    @respx.mock
    def test_sends_name_organism_and_metadata_in_payload(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL).mock(
            return_value=httpx.Response(HTTPStatus.CREATED, json=_job_json(
                1, "RUNNING", ["ERR1"],
            )),
        )
        sheet = _write_import_sheet(tmp_path, {
            "accession": "ERR1", "name": "liver_r1", "organism": "Hs",
            "cell_type": "Neuron",
        })

        run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
        )

        payload = json.loads(route.calls[0].request.content)
        assert payload == {
            "imports": [{
                "accession": "ERR1",
                "sample_type": "rna_seq",
                "name": "liver_r1",
                "organism": "Hs",
                "metadata": {"cell_type": "Neuron"},
            }],
        }

    @respx.mock
    def test_api_rejection_propagates_as_error(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL).mock(
            return_value=httpx.Response(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                json={"error": "sample type 'bogus' does not exist"},
            ),
        )
        sheet = _write_import_sheet(tmp_path, {"accession": "ERR1"})

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "bogus",
        )

        assert result.exit_code == 1
        assert route.call_count == 1
        assert "bogus" in result.stderr

    @respx.mock
    def test_non_csv_sheet_is_usage_error(self, run_cli, tmp_path: Path) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL)
        xlsx = tmp_path / "sheet.xlsx"
        xlsx.write_bytes(b"PK\x03\x04")

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(xlsx), "--sample-type", "rna_seq",
        )

        assert result.exit_code == 2
        assert route.call_count == 0
        assert "CSV" in result.stderr

    def test_missing_sheet_is_usage_error(self, run_cli) -> None:
        result = run_cli(
            "--token", TOKEN, "samples", "import", "--sample-type", "rna_seq",
        )

        assert result.exit_code == 2

    @respx.mock
    def test_missing_sample_type_is_usage_error(self, run_cli, tmp_path: Path) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL)
        sheet = _write_import_sheet(tmp_path, {"accession": "ERR1"})

        result = run_cli(
            "--token", TOKEN, "samples", "import", "--sheet", str(sheet),
        )

        assert result.exit_code == 2
        assert route.call_count == 0

    @respx.mock
    def test_header_only_sheet_is_usage_error(self, run_cli, tmp_path: Path) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL)
        sheet = _write_import_sheet(tmp_path)

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
        )

        assert result.exit_code == 2
        assert route.call_count == 0
        assert str(sheet) in result.stderr

    @respx.mock
    def test_row_sample_type_overrides_the_default(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL).mock(
            return_value=httpx.Response(HTTPStatus.CREATED, json=_job_json(
                1, "RUNNING", ["ERR1", "ERR2"],
            )),
        )
        sheet = _write_import_sheet(
            tmp_path,
            {"accession": "ERR1", "sample_type": "chip_seq"},
            {"accession": "ERR2"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
        )

        assert result.exit_code == 0
        payload = json.loads(route.calls[0].request.content)
        sample_types = [entry["sample_type"] for entry in payload["imports"]]
        assert sample_types == ["chip_seq", "rna_seq"]

    @respx.mock
    def test_sample_type_flag_is_optional_when_every_row_has_its_own(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL).mock(
            return_value=httpx.Response(HTTPStatus.CREATED, json=_job_json(
                1, "RUNNING", ["ERR1", "ERR2"],
            )),
        )
        sheet = _write_import_sheet(
            tmp_path,
            {"accession": "ERR1", "sample_type": "chip_seq"},
            {"accession": "ERR2", "sample_type": "atac_seq"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import", "--sheet", str(sheet),
        )

        assert result.exit_code == 0
        payload = json.loads(route.calls[0].request.content)
        sample_types = [entry["sample_type"] for entry in payload["imports"]]
        assert sample_types == ["chip_seq", "atac_seq"]

    @respx.mock
    def test_row_missing_sample_type_without_default_is_usage_error(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL)
        sheet = _write_import_sheet(
            tmp_path,
            {"accession": "ERR1", "sample_type": "chip_seq"},
            {"accession": "ERR2"},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import", "--sheet", str(sheet),
        )

        assert result.exit_code == 2
        assert route.call_count == 0
        assert "data row(s) 2" in result.stderr

    @respx.mock
    def test_sheet_with_only_blank_accessions_is_usage_error(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL)
        sheet = _write_import_sheet(tmp_path, {"accession": ""}, {"accession": ""})

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
        )

        assert result.exit_code == 2
        assert route.call_count == 0
        assert str(sheet) in result.stderr

    @respx.mock
    def test_mixed_valid_and_blank_accession_rows_is_usage_error(
        self, run_cli, tmp_path: Path,
    ) -> None:
        # A blank accession is rejected outright rather than silently
        # skipped, even when the rest of the sheet is otherwise fine.
        route = respx.post(SAMPLE_IMPORTS_URL)
        sheet = _write_import_sheet(
            tmp_path,
            {"accession": "ERR1"},
            {"accession": ""},
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
        )

        assert result.exit_code == 2
        assert route.call_count == 0

    @respx.mock
    def test_sheet_with_no_accession_column_is_usage_error(
        self, run_cli, tmp_path: Path,
    ) -> None:
        route = respx.post(SAMPLE_IMPORTS_URL)
        sheet = tmp_path / "accessions.csv"
        with sheet.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["run", "name"])
            writer.writeheader()
            writer.writerow({"run": "ERR1160845", "name": "liver_r1"})

        result = run_cli(
            "--token", TOKEN, "samples", "import",
            "--sheet", str(sheet), "--sample-type", "rna_seq",
        )

        assert result.exit_code == 2
        assert route.call_count == 0
        assert str(sheet) in result.stderr


class TestSamplesImportStatus:

    @respx.mock
    def test_reports_running_job(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json=_job_json(
                42, "RUNNING", ["ERR1", "ERR2"],
            )),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42",
        )

        assert result.exit_code == 0
        assert "42" in result.stdout
        assert "RUNNING" in result.stdout

    @respx.mock
    def test_running_job_with_started_reports_when_it_started(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json={
                "id": 42, "status": "RUNNING", "created": 1700000000,
                "started": 1700000001, "finished": None,
                "accessions": ["ERR1"], "sample_ids": [], "execution_id": None, "error": None,
            }),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42",
        )

        assert result.exit_code == 0
        assert "started 2023-11-14" in result.stdout

    @respx.mock
    def test_started_with_non_utc_offset_is_reported_in_utc(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json={
                "id": 42, "status": "RUNNING", "created": 1700000000,
                "started": "2024-04-05T19:34:38+02:00", "finished": None,
                "accessions": ["ERR1"], "sample_ids": [], "execution_id": None, "error": None,
            }),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42",
        )

        assert result.exit_code == 0
        assert "started 2024-04-05 17:34:38 UTC" in result.stdout

    @respx.mock
    def test_started_with_no_offset_is_treated_as_utc(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json={
                "id": 42, "status": "RUNNING", "created": 1700000000,
                "started": "2024-04-05T19:34:38", "finished": None,
                "accessions": ["ERR1"], "sample_ids": [], "execution_id": None, "error": None,
            }),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42",
        )

        assert result.exit_code == 0
        assert "started 2024-04-05 19:34:38 UTC" in result.stdout

    @respx.mock
    def test_naive_started_is_reported_as_utc_in_json_too(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json={
                "id": 42, "status": "RUNNING", "created": 1700000000,
                "started": "2024-04-05T19:34:38", "finished": None,
                "accessions": ["ERR1"], "sample_ids": [], "execution_id": None, "error": None,
            }),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42", "--json",
        )

        assert result.exit_code == 0
        document = json.loads(result.stdout)
        assert document["started"] == "2024-04-05T19:34:38Z"

    @respx.mock
    def test_running_job_falls_back_to_created_when_not_started(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json={
                "id": 42, "status": "RUNNING", "created": 1700000000,
                "started": None, "finished": None,
                "accessions": ["ERR1"], "sample_ids": [], "execution_id": None, "error": None,
            }),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42",
        )

        assert result.exit_code == 0
        assert "created 2023-11-14" in result.stdout

    @respx.mock
    def test_completed_job_reports_when_it_finished(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json=_job_json(
                42, "COMPLETED", ["ERR1"], [101],
            )),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42",
        )

        assert result.exit_code == 0
        assert "finished 2023-11-14" in result.stdout

    @respx.mock
    def test_reports_completed_job_with_sample_ids(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json=_job_json(
                42, "COMPLETED", ["ERR1", "ERR2"], [101, 102],
            )),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42",
        )

        assert result.exit_code == 0
        assert "101" in result.stdout
        assert "102" in result.stdout

    @respx.mock
    def test_reports_failed_job_with_error(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json=_job_json(
                42, "FAILED", ["ERR1"], error="download failed",
            )),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42",
        )

        assert result.exit_code == 1
        assert "FAILED" in result.stdout
        assert "download failed" not in result.stdout
        assert "download failed" in result.stderr

    @respx.mock
    def test_failed_job_json_mode_has_error_on_stdout_only(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json=_job_json(
                42, "FAILED", ["ERR1"], error="download failed",
            )),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42", "--json",
        )

        assert result.exit_code == 1
        assert result.stderr == ""
        document = json.loads(result.stdout)
        assert document["error"] == "download failed"

    def test_non_numeric_job_id_reports_clear_message(self, run_cli) -> None:
        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "not-a-number",
        )

        assert result.exit_code == 2
        assert "_job_id" not in result.stderr
        assert "job id" in result.stderr.lower()

    @respx.mock
    def test_completed_job_with_no_sample_ids_reports_none(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json=_job_json(
                42, "COMPLETED", ["ERR1"], [],
            )),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42",
        )

        assert result.exit_code == 0
        assert "none" in result.stdout

    @respx.mock
    def test_json_document_matches_job_shape(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json=_job_json(
                42, "COMPLETED", ["ERR1"], [101],
            )),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42", "--json",
        )

        assert result.exit_code == 0
        document = json.loads(result.stdout)
        assert result.stdout.count("\n") == 1
        assert document == {
            "id": 42,
            "status": "COMPLETED",
            "created": "2023-11-14T22:13:20Z",
            "started": "2023-11-14T22:13:21Z",
            "finished": "2023-11-14T22:13:22Z",
            "accessions": ["ERR1"],
            "sample_ids": [101],
            "execution_id": 7,
            "error": None,
        }

    @respx.mock
    def test_reports_job_with_no_execution_yet(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/42").mock(
            return_value=httpx.Response(HTTPStatus.OK, json=_job_json(
                42, "RUNNING", ["ERR1"], execution_id=None,
            )),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "42", "--json",
        )

        assert result.exit_code == 0
        document = json.loads(result.stdout)
        assert document["execution_id"] is None

    @respx.mock
    def test_unknown_job_id_is_not_found(self, run_cli) -> None:
        respx.get(f"{SAMPLE_IMPORTS_URL}/999").mock(
            return_value=httpx.Response(
                HTTPStatus.NOT_FOUND, json={"error": "sample import 999 does not exist"},
            ),
        )

        result = run_cli(
            "--token", TOKEN, "samples", "import-status", "--job-id", "999",
        )

        assert result.exit_code == 4

    def test_missing_job_id_is_usage_error(self, run_cli) -> None:
        result = run_cli("--token", TOKEN, "samples", "import-status")

        assert result.exit_code == 2
