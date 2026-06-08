import json
from http import HTTPStatus
from pathlib import Path

import httpx
import respx

from tests.unit.cli.conftest import DEFAULT_BASE_URL
from tests.unit.v2.conftest import parse_multipart

UPLOAD_URL = f"{DEFAULT_BASE_URL}/upload"
TOKEN = "test.token"


def _counts_file(tmp_path: Path) -> Path:
    path = tmp_path / "counts.tsv"
    path.write_bytes(b"gene\tcount")
    return path


class TestDataUpload:

    @respx.mock
    def test_uploads_and_prints_identifier(self, run_cli, tmp_path: Path) -> None:
        data_id = "data_xyz"
        respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(HTTPStatus.OK, json={"id": data_id}),
        )

        result = run_cli(
            "--token", TOKEN, "data", "upload", str(_counts_file(tmp_path)),
            "--no-progress",
        )

        assert result.exit_code == 0
        assert data_id in result.stdout

    @respx.mock
    def test_json_emits_single_document_on_stdout_only(
        self, run_cli, tmp_path: Path,
    ) -> None:
        data_id = "data_xyz"
        respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(HTTPStatus.OK, json={"id": data_id}),
        )

        result = run_cli(
            "data", "upload", str(_counts_file(tmp_path)),
            "--token", TOKEN, "--no-progress", "--json",
        )

        assert result.exit_code == 0
        assert json.loads(result.stdout) == {"id": data_id}
        assert result.stdout.count("\n") == 1

    @respx.mock
    def test_filename_overrides_stored_name(self, run_cli, tmp_path: Path) -> None:
        stored_name = "renamed.tsv"
        route = respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(HTTPStatus.OK, json={"id": "d1"}),
        )

        run_cli(
            "data", "upload", str(_counts_file(tmp_path)),
            "--filename", stored_name, "--token", TOKEN, "--no-progress",
        )

        fields, files = parse_multipart(route.calls[0].request)
        assert fields["filename"] == stored_name
        assert files["blob"][0] == stored_name

    @respx.mock
    def test_data_type_sent_when_provided(self, run_cli, tmp_path: Path) -> None:
        data_type = "bam"
        route = respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(HTTPStatus.OK, json={"id": "d1"}),
        )

        run_cli(
            "data", "upload", str(_counts_file(tmp_path)),
            "--data-type", data_type, "--token", TOKEN, "--no-progress",
        )

        fields, _ = parse_multipart(route.calls[0].request)
        assert fields["data_type"] == data_type

    @respx.mock
    def test_directory_uploads_as_archive(self, run_cli, tmp_path: Path) -> None:
        route = respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(HTTPStatus.OK, json={"id": "d1"}),
        )

        run_cli(
            "data", "upload", str(_counts_file(tmp_path)),
            "--directory", "--token", TOKEN, "--no-progress",
        )

        fields, _ = parse_multipart(route.calls[0].request)
        assert fields["is_directory"] == "true"

    @respx.mock
    def test_server_rejection_exits_bad_request(self, run_cli, tmp_path: Path) -> None:
        respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(
                HTTPStatus.BAD_REQUEST, json={"error": "Unknown data type"},
            ),
        )

        result = run_cli(
            "data", "upload", str(_counts_file(tmp_path)),
            "--data-type", "bogus", "--token", TOKEN, "--no-progress",
        )

        assert result.exit_code == 5

    @respx.mock
    def test_invalid_token_exits_auth(self, run_cli, tmp_path: Path) -> None:
        # A 401 makes the transport attempt a token refresh; failing it lets the
        # original 401 surface as an AuthenticationError.
        respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(HTTPStatus.UNAUTHORIZED),
        )
        respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(
                HTTPStatus.UNAUTHORIZED, json={"error": "Unauthenticated"},
            ),
        )

        result = run_cli(
            "data", "upload", str(_counts_file(tmp_path)),
            "--token", TOKEN, "--no-progress",
        )

        assert result.exit_code == 3

    @respx.mock
    def test_json_error_document_carries_message_and_status(
        self, run_cli, tmp_path: Path,
    ) -> None:
        error_message = "Unknown data type"
        respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(
                HTTPStatus.BAD_REQUEST, json={"error": error_message},
            ),
        )

        result = run_cli(
            "data", "upload", str(_counts_file(tmp_path)),
            "--token", TOKEN, "--no-progress", "--json",
        )

        assert result.exit_code == 5
        assert result.stdout == ""
        document = json.loads(result.stderr)
        assert document["message"] == error_message
        assert document["status_code"] == int(HTTPStatus.BAD_REQUEST)
