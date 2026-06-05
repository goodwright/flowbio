from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx

from flowbio.v2._transport import HttpTransport
from flowbio.v2._uploads import ChunkedUploader
from flowbio.v2.client import ClientConfig
from flowbio.v2.exceptions import BadRequestError

from tests.unit.v2.conftest import DEFAULT_BASE_URL, parse_multipart

ENDPOINT = "/upload/test"
ENDPOINT_URL = f"{DEFAULT_BASE_URL}{ENDPOINT}"


def _make_uploader(config: ClientConfig | None = None) -> ChunkedUploader:
    transport = HttpTransport(DEFAULT_BASE_URL)
    return ChunkedUploader(transport, config or ClientConfig(show_progress=False))


class TestUploadInChunks:

    @respx.mock
    def test_single_chunk_posts_once_and_returns_response(self, tmp_path: Path) -> None:
        response_body = {"id": "data_1", "extra": "kept"}
        file_path = tmp_path / "counts.tsv"
        file_path.write_bytes(b"gene\tcount")
        route = respx.post(ENDPOINT_URL).mock(
            return_value=httpx.Response(200, json=response_body),
        )

        result = _make_uploader().upload_in_chunks(ENDPOINT, file_path)

        assert result == response_body
        assert route.call_count == 1
        fields, files = parse_multipart(route.calls[0].request)
        assert fields["filename"] == "counts.tsv"
        assert fields["expected_file_size"] == "0"
        assert fields["is_last"] == "true"
        assert files["blob"] == ("counts.tsv", b"gene\tcount")

    @respx.mock
    def test_threads_chunks_with_byte_offsets(self, tmp_path: Path) -> None:
        chunk_size = 40
        file_path = tmp_path / "big.bin"
        file_path.write_bytes(b"A" * 100)
        route = respx.post(ENDPOINT_URL)
        route.side_effect = [
            httpx.Response(200, json={"id": "d1"}),
            httpx.Response(200, json={"id": "d2"}),
            httpx.Response(200, json={"id": "d3"}),
        ]

        result = _make_uploader(
            ClientConfig(chunk_size=chunk_size, show_progress=False),
        ).upload_in_chunks(ENDPOINT, file_path)

        assert result == {"id": "d3"}
        first, _ = parse_multipart(route.calls[0].request)
        second, _ = parse_multipart(route.calls[1].request)
        third, _ = parse_multipart(route.calls[2].request)
        assert [first["data"], second["data"], third["data"]] == ["", "d1", "d2"]
        assert [
            first["expected_file_size"],
            second["expected_file_size"],
            third["expected_file_size"],
        ] == ["0", "40", "80"]
        assert [first["is_last"], second["is_last"], third["is_last"]] == ["false", "false", "true"]

    @respx.mock
    def test_threads_data_id_response_shape(self, tmp_path: Path) -> None:
        first_data_id = "data_1"
        file_path = tmp_path / "big.bin"
        file_path.write_bytes(b"A" * 100)
        route = respx.post(ENDPOINT_URL)
        route.side_effect = [
            httpx.Response(200, json={"data_id": first_data_id}),
            httpx.Response(200, json={"data_id": "data_2"}),
        ]

        _make_uploader(
            ClientConfig(chunk_size=60, show_progress=False),
        ).upload_in_chunks(ENDPOINT, file_path)

        second, _ = parse_multipart(route.calls[1].request)
        assert second["data"] == first_data_id

    @respx.mock
    def test_filename_defaults_to_path_name(self, tmp_path: Path) -> None:
        file_path = tmp_path / "local.tsv"
        file_path.write_bytes(b"data")
        route = respx.post(ENDPOINT_URL).mock(
            return_value=httpx.Response(200, json={"id": "d1"}),
        )

        _make_uploader().upload_in_chunks(ENDPOINT, file_path)

        fields, files = parse_multipart(route.calls[0].request)
        assert fields["filename"] == "local.tsv"
        assert files["blob"][0] == "local.tsv"

    @respx.mock
    def test_filename_override_applies_to_field_and_blob_on_every_chunk(self, tmp_path: Path) -> None:
        stored_name = "renamed.tsv"
        file_path = tmp_path / "local.tsv"
        file_path.write_bytes(b"A" * 100)
        route = respx.post(ENDPOINT_URL)
        route.side_effect = [
            httpx.Response(200, json={"id": "d1"}),
            httpx.Response(200, json={"id": "d2"}),
        ]

        _make_uploader(
            ClientConfig(chunk_size=60, show_progress=False),
        ).upload_in_chunks(ENDPOINT, file_path, filename=stored_name)

        for call in route.calls:
            fields, files = parse_multipart(call.request)
            assert fields["filename"] == stored_name
            assert files["blob"][0] == stored_name

    @respx.mock
    def test_extra_fields_sent_on_every_chunk(self, tmp_path: Path) -> None:
        file_path = tmp_path / "big.bin"
        file_path.write_bytes(b"A" * 100)
        route = respx.post(ENDPOINT_URL)
        route.side_effect = [
            httpx.Response(200, json={"id": "d1"}),
            httpx.Response(200, json={"id": "d2"}),
        ]

        _make_uploader(
            ClientConfig(chunk_size=60, show_progress=False),
        ).upload_in_chunks(ENDPOINT, file_path, extra_fields={"data_type": "bam"})

        for call in route.calls:
            fields, _ = parse_multipart(call.request)
            assert fields["data_type"] == "bam"

    @respx.mock
    @patch("time.sleep")
    def test_retries_chunk_on_transient_error(self, _mock_sleep, tmp_path: Path) -> None:
        data_id = "d1"
        file_path = tmp_path / "reads.tsv"
        file_path.write_bytes(b"data")
        route = respx.post(ENDPOINT_URL)
        route.side_effect = [
            httpx.Response(502, content=b"<html>bad gw</html>"),
            httpx.Response(200, json={"id": data_id}),
        ]

        result = _make_uploader().upload_in_chunks(ENDPOINT, file_path)

        assert result == {"id": data_id}
        assert route.call_count == 2

    @respx.mock
    @patch("time.sleep")
    def test_does_not_retry_on_client_error(self, _mock_sleep, tmp_path: Path) -> None:
        file_path = tmp_path / "reads.tsv"
        file_path.write_bytes(b"data")
        route = respx.post(ENDPOINT_URL).mock(
            return_value=httpx.Response(400, json={"error": "nope"}),
        )

        with pytest.raises(BadRequestError):
            _make_uploader().upload_in_chunks(ENDPOINT, file_path)

        assert route.call_count == 1
