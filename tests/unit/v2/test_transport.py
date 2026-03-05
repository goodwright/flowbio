import json

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

