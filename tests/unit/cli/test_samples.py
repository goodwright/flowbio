import json
from http import HTTPStatus
from pathlib import Path

import httpx
import respx

from tests.unit.cli.conftest import DEFAULT_BASE_URL
from tests.unit.v2.conftest import parse_multipart

SAMPLE_UPLOAD_URL = f"{DEFAULT_BASE_URL}/upload/sample"
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
