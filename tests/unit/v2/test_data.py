from http import HTTPStatus
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from flowbio.v2.client import Client, ClientConfig
from flowbio.v2.data import Data, DataResource
from flowbio.v2.exceptions import AuthenticationError, BadRequestError

from tests.unit.v2.conftest import DEFAULT_BASE_URL, parse_multipart

UPLOAD_URL = f"{DEFAULT_BASE_URL}/upload"


class TestDataResourceWiring:

    def test_client_has_data_attribute(self) -> None:
        client = Client()

        assert isinstance(client.data, DataResource)

    def test_data_is_read_only(self) -> None:
        client = Client()

        with pytest.raises(AttributeError):
            client.data = "something else"


class TestUploadData:

    @respx.mock
    def test_single_chunk_upload(self, tmp_path: Path) -> None:
        data_id = "data_xyz"
        file_path = tmp_path / "counts.tsv"
        file_path.write_bytes(b"gene\tcount")
        route = respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(200, json={"id": data_id}),
        )

        client = Client()
        result = client.data.upload_data(file_path)

        assert result == Data(id=data_id)
        assert route.call_count == 1
        fields, files = parse_multipart(route.calls[0].request)
        assert fields["filename"] == "counts.tsv"
        assert fields["expected_file_size"] == "0"
        assert fields["is_last"] == "true"
        assert files["blob"][0] == "counts.tsv"

    @respx.mock
    def test_multi_chunk_threading(self, tmp_path: Path) -> None:
        chunk_size = 40
        file_path = tmp_path / "big.tsv"
        file_path.write_bytes(b"A" * 100)
        route = respx.post(UPLOAD_URL)
        route.side_effect = [
            httpx.Response(200, json={"id": "d1"}),
            httpx.Response(200, json={"id": "d2"}),
            httpx.Response(200, json={"id": "d3"}),
        ]

        client = Client(config=ClientConfig(chunk_size=chunk_size, show_progress=False))
        result = client.data.upload_data(file_path)

        assert result == Data(id="d3")
        assert route.call_count == 3
        first, _ = parse_multipart(route.calls[0].request)
        second, _ = parse_multipart(route.calls[1].request)
        third, _ = parse_multipart(route.calls[2].request)
        assert first["data"] == ""
        assert second["data"] == "d1"
        assert third["data"] == "d2"
        assert [first["expected_file_size"], second["expected_file_size"], third["expected_file_size"]] == ["0", "40", "80"]
        assert [first["is_last"], second["is_last"], third["is_last"]] == ["false", "false", "true"]

    @respx.mock
    def test_filename_defaults_to_path_name(self, tmp_path: Path) -> None:
        file_path = tmp_path / "local_name.tsv"
        file_path.write_bytes(b"data")
        route = respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(200, json={"id": "d1"}),
        )

        client = Client()
        client.data.upload_data(file_path)

        fields, files = parse_multipart(route.calls[0].request)
        assert fields["filename"] == "local_name.tsv"
        assert files["blob"][0] == "local_name.tsv"

    @respx.mock
    def test_filename_override_applies_to_every_chunk(self, tmp_path: Path) -> None:
        stored_name = "renamed.tsv"
        file_path = tmp_path / "local_name.tsv"
        file_path.write_bytes(b"A" * 100)
        route = respx.post(UPLOAD_URL)
        route.side_effect = [
            httpx.Response(200, json={"id": "d1"}),
            httpx.Response(200, json={"id": "d2"}),
            httpx.Response(200, json={"id": "d3"}),
        ]

        client = Client(config=ClientConfig(chunk_size=40, show_progress=False))
        client.data.upload_data(file_path, filename=stored_name)

        for call in route.calls:
            fields, files = parse_multipart(call.request)
            assert fields["filename"] == stored_name
            assert files["blob"][0] == stored_name

    @respx.mock
    def test_data_type_sent_when_provided(self, tmp_path: Path) -> None:
        data_type = "bam"
        file_path = tmp_path / "reads.bam"
        file_path.write_bytes(b"data")
        route = respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(200, json={"id": "d1"}),
        )

        client = Client()
        client.data.upload_data(file_path, data_type=data_type)

        fields, _ = parse_multipart(route.calls[0].request)
        assert fields["data_type"] == data_type

    @respx.mock
    def test_data_type_omitted_by_default(self, tmp_path: Path) -> None:
        file_path = tmp_path / "reads.bam"
        file_path.write_bytes(b"data")
        route = respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(200, json={"id": "d1"}),
        )

        client = Client()
        client.data.upload_data(file_path)

        fields, _ = parse_multipart(route.calls[0].request)
        assert "data_type" not in fields

    @respx.mock
    def test_is_directory_sent_when_true(self, tmp_path: Path) -> None:
        file_path = tmp_path / "archive.zip"
        file_path.write_bytes(b"data")
        route = respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(200, json={"id": "d1"}),
        )

        client = Client()
        client.data.upload_data(file_path, is_directory=True)

        fields, _ = parse_multipart(route.calls[0].request)
        assert fields["is_directory"] == "true"

    @respx.mock
    def test_is_directory_omitted_by_default(self, tmp_path: Path) -> None:
        file_path = tmp_path / "archive.zip"
        file_path.write_bytes(b"data")
        route = respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(200, json={"id": "d1"}),
        )

        client = Client()
        client.data.upload_data(file_path)

        fields, _ = parse_multipart(route.calls[0].request)
        assert "is_directory" not in fields

    @respx.mock
    def test_spaces_in_filename_raises_bad_request(self, tmp_path: Path) -> None:
        error_body = {"filename": ["Spaces in filename"]}
        file_path = tmp_path / "reads.tsv"
        file_path.write_bytes(b"data")
        respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(HTTPStatus.BAD_REQUEST, json=error_body),
        )

        client = Client()

        with pytest.raises(BadRequestError) as exc_info:
            client.data.upload_data(file_path, filename="bad name.tsv")

        assert exc_info.value.message == error_body

    @respx.mock
    def test_unauthenticated_raises_authentication_error(self, tmp_path: Path) -> None:
        file_path = tmp_path / "reads.tsv"
        file_path.write_bytes(b"data")
        respx.post(UPLOAD_URL).mock(
            return_value=httpx.Response(HTTPStatus.UNAUTHORIZED, json={"error": "Unauthenticated"}),
        )

        client = Client()

        with pytest.raises(AuthenticationError):
            client.data.upload_data(file_path)

    @respx.mock
    @patch("time.sleep")
    def test_retries_chunk_on_502(self, _mock_sleep, tmp_path: Path) -> None:
        data_id = "d1"
        file_path = tmp_path / "reads.tsv"
        file_path.write_bytes(b"data")
        route = respx.post(UPLOAD_URL)
        route.side_effect = [
            httpx.Response(HTTPStatus.BAD_GATEWAY, content=b"<html>bad gw</html>"),
            httpx.Response(200, json={"id": data_id}),
        ]

        client = Client(config=ClientConfig(show_progress=False))
        result = client.data.upload_data(file_path)

        assert result == Data(id=data_id)
        assert route.call_count == 2
