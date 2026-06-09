import io
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
    def test_no_output_with_tty_stdout_is_usage_error(
        self, run_cli, monkeypatch,
    ) -> None:
        class _TtyStringIO(io.StringIO):
            def isatty(self) -> bool:
                return True

        monkeypatch.setattr(io, "StringIO", _TtyStringIO)
        route = _mock_annotation_template("generic")

        result = run_cli("--token", TOKEN, "samples", "annotation-template")

        assert result.exit_code == 2
        assert route.call_count == 0

    @respx.mock
    def test_json_without_output_is_usage_error(
        self, run_cli,
    ) -> None:
        route = _mock_annotation_template("generic")

        result = run_cli("--token", TOKEN, "samples", "annotation-template", "--json")

        assert result.exit_code == 2
        assert route.call_count == 0

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
        respx.post(ANNOTATION_UPLOAD_URL).mock(
            return_value=httpx.Response(
                HTTPStatus.BAD_REQUEST,
                json={"validation": [{"row": 1, "message": "Invalid scientist"}]},
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
