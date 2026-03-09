import json
from http import HTTPStatus
from unittest.mock import patch

import httpx
import respx

import pytest

from flowbio.v2._transport import HttpTransport
from flowbio.v2.exceptions import (
    AuthenticationError,
    BadRequestError,
    FlowApiError,
    NotFoundError,
)

from tests.unit.v2.conftest import DEFAULT_BASE_URL


class TestTransportConnectionRetries:

    @patch("flowbio.v2._transport.httpx.HTTPTransport")
    def test_default_retries(self, mock_http_transport) -> None:
        HttpTransport(DEFAULT_BASE_URL)

        mock_http_transport.assert_called_once_with(retries=3)

    @patch("flowbio.v2._transport.httpx.HTTPTransport")
    def test_custom_retries(self, mock_http_transport) -> None:
        connection_retries = 5

        HttpTransport(DEFAULT_BASE_URL, connection_retries=connection_retries)

        mock_http_transport.assert_called_once_with(retries=connection_retries)

    @patch("flowbio.v2._transport.httpx.HTTPTransport")
    def test_retries_disabled(self, mock_http_transport) -> None:
        HttpTransport(DEFAULT_BASE_URL, connection_retries=0)

        mock_http_transport.assert_called_once_with(retries=0)


class TestTransportGet:

    @respx.mock
    def test_sends_request_to_base_url_plus_path(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(200, json={"username": "testuser"}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.get("/me")

        assert route.called

    @respx.mock
    def test_returns_parsed_json(self) -> None:
        expected = {"username": "testuser"}
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(200, json=expected),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        result = transport.get("/me")

        assert result == expected

    @respx.mock
    def test_sends_user_agent_header(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(200, json={}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.get("/me")

        user_agent = route.calls[0].request.headers["user-agent"]
        assert "flowbio-python/" in user_agent

    @respx.mock
    def test_path_without_leading_slash(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(200, json={}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.get("me")

        assert route.called

    @respx.mock
    def test_sends_query_parameters(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/items").mock(
            return_value=httpx.Response(200, json={}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.get("/items", params={"page": 2, "count": 10})

        assert route.called
        assert route.calls[0].request.url.params["page"] == "2"
        assert route.calls[0].request.url.params["count"] == "10"


class TestTransportPost:

    @respx.mock
    def test_sends_json_body(self) -> None:
        request_body = {"username": "testuser", "password": "testpass"}
        route = respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(200, json={"token": "jwt"}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.post("/login", json=request_body)

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == request_body

    @respx.mock
    def test_returns_parsed_json(self) -> None:
        expected = {"token": "jwt.token.here"}
        respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(200, json=expected),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        result = transport.post("/login", json={"username": "x", "password": "y"})

        assert result == expected

    @respx.mock
    def test_path_without_leading_slash(self) -> None:
        route = respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(200, json={}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.post("login", json={})

        assert route.called


class TestTransportPostMultipart:

    @respx.mock
    def test_sends_multipart_form_data(self) -> None:
        route = respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            return_value=httpx.Response(200, json={"id": "123"}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.post(
            "/upload/sample",
            data={"sample_name": "test"},
            files={"file": ("test.txt", b"file content", "text/plain")},
        )

        assert route.called
        content_type = route.calls[0].request.headers["content-type"]
        assert "multipart/form-data" in content_type

    @respx.mock
    def test_returns_parsed_json(self) -> None:
        expected = {"id": "123", "data_id": "456"}
        respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            return_value=httpx.Response(200, json=expected),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        result = transport.post(
            "/upload/sample",
            data={"sample_name": "test"},
            files={"file": ("test.txt", b"content", "text/plain")},
        )

        assert result == expected

    @respx.mock
    def test_raises_bad_request_error_on_400(self) -> None:
        error_message = "Invalid sample"
        respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            return_value=httpx.Response(400, json={"error": error_message}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(BadRequestError) as exc_info:
            transport.post(
                "/upload/sample",
                data={"sample_name": "test"},
                files={"file": ("test.txt", b"content", "text/plain")},
            )

        assert exc_info.value.message == error_message

    @respx.mock
    def test_raises_authentication_error_on_401(self) -> None:
        error_message = "Not authenticated"
        respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            return_value=httpx.Response(401, json={"error": error_message}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(AuthenticationError) as exc_info:
            transport.post(
                "/upload/sample",
                data={"sample_name": "test"},
                files={"file": ("test.txt", b"content", "text/plain")},
            )

        assert exc_info.value.message == error_message


class TestTransportErrorHandling:

    @respx.mock
    def test_post_raises_bad_request_error_on_400(self) -> None:
        error_message = "Invalid credentials"
        respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(400, json={"error": error_message}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(BadRequestError) as exc_info:
            transport.post("/login", json={"username": "x", "password": "y"})

        assert exc_info.value.status_code == 400
        assert exc_info.value.message == error_message

    @respx.mock
    def test_get_raises_bad_request_error_on_400(self) -> None:
        error_message = "No refresh token supplied"
        respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(400, json={"error": error_message}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(BadRequestError) as exc_info:
            transport.get("/token")

        assert exc_info.value.status_code == 400
        assert exc_info.value.message == error_message

    @respx.mock
    def test_raises_authentication_error_on_401(self) -> None:
        error_message = "Not authenticated"
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(401, json={"error": error_message}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(AuthenticationError) as exc_info:
            transport.get("/me")

        assert exc_info.value.status_code == 401
        assert exc_info.value.message == error_message

    @respx.mock
    def test_raises_not_found_error_on_404(self) -> None:
        error_message = "Not found"
        respx.get(f"{DEFAULT_BASE_URL}/users/999").mock(
            return_value=httpx.Response(404, json={"error": error_message}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(NotFoundError) as exc_info:
            transport.get("/users/999")

        assert exc_info.value.status_code == 404
        assert exc_info.value.message == error_message

    @respx.mock
    def test_raises_flow_api_error_for_unexpected_status_codes(self) -> None:
        error_message = "Internal server error"
        respx.get(f"{DEFAULT_BASE_URL}/something").mock(
            return_value=httpx.Response(500, json={"error": error_message}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(FlowApiError) as exc_info:
            transport.get("/something")

        assert exc_info.value.status_code == 500
        assert exc_info.value.message == error_message


class TestTransportErrorBodyPreservation:

    @respx.mock
    def test_400_without_error_key_preserves_full_body(self) -> None:
        body = {"validation": [{"row": 1, "message": "Invalid scientist"}]}
        respx.post(f"{DEFAULT_BASE_URL}/upload/annotation").mock(
            return_value=httpx.Response(HTTPStatus.BAD_REQUEST, json=body),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(BadRequestError) as exc_info:
            transport.post("/upload/annotation", data={})

        assert exc_info.value.message == body


class TestTransportGetBytes:

    @respx.mock
    def test_returns_raw_response_bytes(self) -> None:
        content = b"\x50\x4b\x03\x04xlsx-content-here"
        respx.get(f"{DEFAULT_BASE_URL}/annotation/generic").mock(
            return_value=httpx.Response(200, content=content),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        result = transport.get_bytes("/annotation/generic")

        assert result == content

    @respx.mock
    def test_passes_query_parameters(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/annotation/generic").mock(
            return_value=httpx.Response(200, content=b"data"),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.get_bytes("/annotation/generic", params={"format": "xlsx"})

        assert route.calls[0].request.url.params["format"] == "xlsx"

    @respx.mock
    def test_raises_not_found_error_on_404(self) -> None:
        error_message = "Sample type not found"
        respx.get(f"{DEFAULT_BASE_URL}/annotation/nonexistent").mock(
            return_value=httpx.Response(404, json={"error": error_message}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(NotFoundError) as exc_info:
            transport.get_bytes("/annotation/nonexistent")

        assert exc_info.value.status_code == 404
        assert exc_info.value.message == error_message

    @respx.mock
    def test_raises_authentication_error_on_401(self) -> None:
        error_message = "Not authenticated"
        respx.get(f"{DEFAULT_BASE_URL}/annotation/generic").mock(
            return_value=httpx.Response(401, json={"error": error_message}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(AuthenticationError) as exc_info:
            transport.get_bytes("/annotation/generic")

        assert exc_info.value.status_code == 401
        assert exc_info.value.message == error_message


class TestTransportTokenManagement:

    @respx.mock
    def test_set_token_adds_authorization_header(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(200, json={}),
        )
        token = "jwt.token.here"

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.set_token(token)
        transport.get("/me")

        assert route.calls[0].request.headers["authorization"] == f"Bearer {token}"

