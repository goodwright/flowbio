import json

import httpx
import pytest
import respx

from flowbio.v2.auth import UsernamePasswordCredentials
from flowbio.v2.client import Client, ClientConfig
from flowbio.v2.exceptions import BadRequestError

from tests.unit.v2.conftest import DEFAULT_BASE_URL


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


class TestClientConfig:

    def test_default_config_values(self) -> None:
        config = ClientConfig()

        assert config.chunk_size == 1_000_000
        assert config.show_progress is True

    def test_config_is_immutable(self) -> None:
        config = ClientConfig()

        with pytest.raises(AttributeError):
            config.chunk_size = 5_000_000

    def test_client_accepts_custom_config(self) -> None:
        Client(config=ClientConfig(chunk_size=5_000_000))
