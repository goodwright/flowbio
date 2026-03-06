import json

import httpx
import pytest
import respx

from flowbio.v2._transport import HttpTransport
from flowbio.v2.auth import Credentials, TokenCredentials, UsernamePasswordCredentials
from flowbio.v2.exceptions import BadRequestError

from tests.unit.v2.conftest import DEFAULT_BASE_URL


class TestUsernamePasswordCredentials:

    def test_is_credentials_subclass(self) -> None:
        credentials = UsernamePasswordCredentials(
            username="alice", password="s3cret",
        )

        assert isinstance(credentials, Credentials)

    @respx.mock
    def test_authenticate_sends_correct_request_body(self) -> None:
        username = "alice"
        password = "s3cret"
        route = respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(
                200, json={"token": "jwt", "user": {}},
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        credentials = UsernamePasswordCredentials(
            username=username, password=password,
        )
        credentials.authenticate(transport)

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == {"username": username, "password": password}

    @respx.mock
    def test_authenticate_sets_token_on_transport(self) -> None:
        token = "jwt.access.token"
        respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(
                200, json={"token": token, "user": {}},
            ),
        )
        verify_route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(200, json={}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        credentials = UsernamePasswordCredentials(
            username="alice", password="s3cret",
        )
        credentials.authenticate(transport)
        transport.get("/me")

        assert verify_route.calls[0].request.headers["authorization"] == f"Bearer {token}"

    @respx.mock
    def test_authenticate_raises_bad_request_error_on_invalid_credentials(self) -> None:
        error_message = "Invalid credentials"
        respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(
                400, json={"error": error_message},
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        credentials = UsernamePasswordCredentials(
            username="wrong", password="creds",
        )

        with pytest.raises(BadRequestError) as exc_info:
            credentials.authenticate(transport)

        assert exc_info.value.message == error_message


class TestTokenCredentials:

    def test_is_credentials_subclass(self) -> None:
        credentials = TokenCredentials(token="some.jwt.token")

        assert isinstance(credentials, Credentials)

    @respx.mock
    def test_authenticate_sets_token_on_transport(self) -> None:
        token = "existing.jwt.token"
        verify_route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(200, json={}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        credentials = TokenCredentials(token=token)
        credentials.authenticate(transport)
        transport.get("/me")

        assert verify_route.calls[0].request.headers["authorization"] == f"Bearer {token}"

    @respx.mock
    def test_authenticate_does_not_make_http_requests(self) -> None:
        spy_route = respx.route().mock(
            return_value=httpx.Response(200, json={}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)
        credentials = TokenCredentials(token="some.jwt.token")
        credentials.authenticate(transport)

        assert spy_route.call_count == 0
