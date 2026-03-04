import json

import httpx
import pytest
import respx

from flowbio.v2.auth import UsernamePasswordCredentials
from flowbio.v2.exceptions import BadRequestError
from flowbio.v2.client import Client

DEFAULT_BASE_URL = "https://app.flow.bio/api"


class TestClientInit:

    @respx.mock
    def test_uses_default_base_url(self) -> None:
        route = respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(
                200, json={"token": "jwt", "user": {}},
            ),
        )

        client = Client()
        client.log_in(UsernamePasswordCredentials(
            username="alice", password="s3cret",
        ))

        assert route.called

    @respx.mock
    def test_uses_custom_base_url(self) -> None:
        custom_url = "https://mycompany.flow.bio/api"
        route = respx.post(f"{custom_url}/login").mock(
            return_value=httpx.Response(
                200, json={"token": "jwt", "user": {}},
            ),
        )

        client = Client(custom_url)
        client.log_in(UsernamePasswordCredentials(
            username="alice", password="s3cret",
        ))

        assert route.called


class TestClientLogIn:

    @respx.mock
    def test_sends_credentials_to_login_endpoint(self) -> None:
        username = "alice"
        password = "s3cret"
        route = respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(
                200, json={"token": "jwt", "user": {}},
            ),
        )

        client = Client()
        client.log_in(UsernamePasswordCredentials(
            username=username, password=password,
        ))

        sent_body = json.loads(route.calls[0].request.content)
        assert sent_body == {"username": username, "password": password}

    @respx.mock
    def test_sets_token_for_subsequent_requests(self) -> None:
        token = "jwt.access.token"
        respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(
                200, json={"token": token, "user": {}},
            ),
        )
        verify_route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(200, json={}),
        )

        client = Client()
        client.log_in(UsernamePasswordCredentials(
            username="alice", password="s3cret",
        ))
        client._transport.get("/me")

        assert verify_route.calls[0].request.headers["authorization"] == f"Bearer {token}"

    @respx.mock
    def test_raises_bad_request_error_on_invalid_credentials(self) -> None:
        error_message = "Invalid credentials"
        respx.post(f"{DEFAULT_BASE_URL}/login").mock(
            return_value=httpx.Response(
                400, json={"error": error_message},
            ),
        )

        client = Client()

        with pytest.raises(BadRequestError) as exc_info:
            client.log_in(UsernamePasswordCredentials(
                username="wrong", password="creds",
            ))

        assert exc_info.value.message == error_message
