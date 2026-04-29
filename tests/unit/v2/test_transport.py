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


class TestTransportNonJsonErrorBody:
    # Upstream proxies (Cloudflare, GCP load balancers, nginx) return their
    # own HTML/plain-text error pages on 5xx. The transport must surface a
    # FlowApiError with a useful message instead of leaking JSONDecodeError.

    @respx.mock
    def test_html_error_body_raises_flow_api_error_with_status(self) -> None:
        html_body = b"<html><body><h1>502 Bad Gateway</h1></body></html>"
        respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            return_value=httpx.Response(
                HTTPStatus.BAD_GATEWAY,
                content=html_body,
                headers={"content-type": "text/html"},
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(FlowApiError) as exc_info:
            transport.post(
                "/upload/sample",
                data={"sample_name": "test"},
                files={"blob": ("c", b"chunk", "application/octet-stream")},
            )

        assert exc_info.value.status_code == HTTPStatus.BAD_GATEWAY
        assert "502 Bad Gateway" in str(exc_info.value)

    @respx.mock
    def test_empty_error_body_raises_flow_api_error_with_status(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(HTTPStatus.GATEWAY_TIMEOUT, content=b""),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(FlowApiError) as exc_info:
            transport.get("/me")

        assert exc_info.value.status_code == HTTPStatus.GATEWAY_TIMEOUT
        assert "504" in str(exc_info.value)


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


class TestTransportRefreshOnUnauthorized:

    @respx.mock
    def test_get_refreshes_and_retries_when_authenticated(self) -> None:
        old_token = "expired.jwt"
        new_token = "fresh.jwt"
        me_route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            side_effect=[
                httpx.Response(401, json={"error": "Not authorized"}),
                httpx.Response(200, json={"username": "alice"}),
            ],
        )
        token_route = respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(200, json={"token": new_token, "user": {}}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.set_token(old_token)
        result = transport.get("/me")

        assert result == {"username": "alice"}
        assert token_route.called
        assert me_route.call_count == 2
        assert me_route.calls[0].request.headers["authorization"] == f"Bearer {old_token}"
        assert me_route.calls[1].request.headers["authorization"] == f"Bearer {new_token}"

    @respx.mock
    def test_post_refreshes_and_retries_chunk_upload(self) -> None:
        old_token = "expired.jwt"
        new_token = "fresh.jwt"
        upload_route = respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            side_effect=[
                httpx.Response(401, json={"error": "Not authorized"}),
                httpx.Response(200, json={"data_id": "d1"}),
            ],
        )
        respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(200, json={"token": new_token, "user": {}}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.set_token(old_token)
        result = transport.post(
            "/upload/sample",
            data={"sample_name": "test"},
            files={"blob": ("test.txt", b"chunk-bytes", "application/octet-stream")},
        )

        assert result == {"data_id": "d1"}
        assert upload_route.call_count == 2
        assert upload_route.calls[1].request.headers["authorization"] == f"Bearer {new_token}"

    @respx.mock
    def test_get_bytes_refreshes_and_retries(self) -> None:
        old_token = "expired.jwt"
        new_token = "fresh.jwt"
        download_route = respx.get(f"{DEFAULT_BASE_URL}/annotation/generic").mock(
            side_effect=[
                httpx.Response(401, json={"error": "Not authorized"}),
                httpx.Response(200, content=b"xlsx-bytes"),
            ],
        )
        respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(200, json={"token": new_token, "user": {}}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.set_token(old_token)
        result = transport.get_bytes("/annotation/generic")

        assert result == b"xlsx-bytes"
        assert download_route.call_count == 2

    @respx.mock
    def test_refresh_failure_surfaces_original_401(self) -> None:
        original_error = "Not authorized"
        me_route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(401, json={"error": original_error}),
        )
        token_route = respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(400, json={"error": "Refresh token not valid"}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.set_token("expired.jwt")

        with pytest.raises(AuthenticationError) as exc_info:
            transport.get("/me")

        assert exc_info.value.status_code == 401
        assert exc_info.value.message == original_error
        assert token_route.called
        assert me_route.call_count == 1

    @respx.mock
    def test_refresh_returning_non_json_body_surfaces_original_401(self) -> None:
        # A misconfigured proxy could return 200 with HTML — the original
        # 401 must still surface rather than a JSONDecodeError.
        original_error = "Not authorized"
        me_route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(401, json={"error": original_error}),
        )
        respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(
                200,
                content=b"<html>maintenance</html>",
                headers={"content-type": "text/html"},
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.set_token("expired.jwt")

        with pytest.raises(AuthenticationError) as exc_info:
            transport.get("/me")

        assert exc_info.value.message == original_error
        assert me_route.call_count == 1

    @respx.mock
    def test_refresh_returning_no_token_surfaces_original_401(self) -> None:
        # /token returns 200 with no token key when no refresh cookie was sent
        # (TokenCredentials path) — the original 401 must still surface.
        original_error = "Not authorized"
        me_route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(401, json={"error": original_error}),
        )
        token_route = respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(200, json={"error": "No refresh token supplied"}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.set_token("token-credentials.jwt")

        with pytest.raises(AuthenticationError) as exc_info:
            transport.get("/me")

        assert exc_info.value.message == original_error
        assert token_route.called
        assert me_route.call_count == 1

    @respx.mock
    def test_refresh_sends_cookie_set_by_login(self) -> None:
        refresh_cookie = "refresh-cookie-from-login"
        respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(
                200,
                json={"token": "access.jwt", "user": {}},
                headers={"Set-Cookie": f"flow_refresh_token={refresh_cookie}; HttpOnly; Path=/"},
            ),
        )
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            side_effect=[
                httpx.Response(401, json={"error": "Not authorized"}),
                httpx.Response(200, json={}),
            ],
        )
        token_route = respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(200, json={"token": "new.jwt", "user": {}}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.post("/login", json={"username": "x", "password": "y"})
        transport.set_token("access.jwt")
        transport.get("/me")

        assert token_route.called
        cookie_header = token_route.calls[0].request.headers.get("cookie", "")
        assert f"flow_refresh_token={refresh_cookie}" in cookie_header

    @respx.mock
    def test_rotated_refresh_cookie_used_on_next_refresh(self) -> None:
        first_cookie = "first-refresh-cookie"
        rotated_cookie = "rotated-refresh-cookie"
        respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(
                200,
                json={"token": "access.jwt", "user": {}},
                headers={"Set-Cookie": f"flow_refresh_token={first_cookie}; HttpOnly; Path=/"},
            ),
        )
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            side_effect=[
                httpx.Response(401, json={"error": "Not authorized"}),
                httpx.Response(200, json={}),
                httpx.Response(401, json={"error": "Not authorized"}),
                httpx.Response(200, json={}),
            ],
        )
        token_route = respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            side_effect=[
                httpx.Response(
                    200,
                    json={"token": "second.jwt", "user": {}},
                    headers={"Set-Cookie": f"flow_refresh_token={rotated_cookie}; HttpOnly; Path=/"},
                ),
                httpx.Response(200, json={"token": "third.jwt", "user": {}}),
            ],
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.post("/login", json={"username": "x", "password": "y"})
        transport.set_token("access.jwt")
        transport.get("/me")
        transport.get("/me")

        assert token_route.call_count == 2
        first_cookie_header = token_route.calls[0].request.headers.get("cookie", "")
        second_cookie_header = token_route.calls[1].request.headers.get("cookie", "")
        assert f"flow_refresh_token={first_cookie}" in first_cookie_header
        assert f"flow_refresh_token={rotated_cookie}" in second_cookie_header

    @respx.mock
    def test_no_refresh_when_no_authorization_header(self) -> None:
        login_route = respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(401, json={"error": "Not authorized"}),
        )
        token_route = respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(200, json={"token": "new.jwt", "user": {}}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(AuthenticationError):
            transport.post("/login", json={"username": "x", "password": "y"})

        assert login_route.call_count == 1
        assert not token_route.called

