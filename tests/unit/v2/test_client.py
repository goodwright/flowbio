import json
from datetime import timedelta
from unittest.mock import patch

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
        assert config.connection_retries == 3
        assert config.request_timeout == timedelta(seconds=60)
        assert config.upload_retries == 3

    def test_custom_connection_retries(self) -> None:
        config = ClientConfig(connection_retries=0)

        assert config.connection_retries == 0

    def test_custom_request_timeout(self) -> None:
        custom_timeout = timedelta(minutes=2)

        config = ClientConfig(request_timeout=custom_timeout)

        assert config.request_timeout == custom_timeout

    def test_config_is_immutable(self) -> None:
        config = ClientConfig()

        with pytest.raises(AttributeError):
            config.chunk_size = 5_000_000

    def test_client_accepts_custom_config(self) -> None:
        Client(config=ClientConfig(chunk_size=5_000_000))

    @patch("flowbio.v2.client.HttpTransport")
    def test_client_passes_connection_retries_to_transport(self, mock_transport) -> None:
        connection_retries = 5

        Client(config=ClientConfig(connection_retries=connection_retries))

        mock_transport.assert_called_once_with(
            "https://app.flow.bio/api",
            connection_retries=connection_retries,
            request_timeout=timedelta(seconds=60),
        )

    @patch("flowbio.v2.client.HttpTransport")
    def test_client_passes_request_timeout_to_transport(self, mock_transport) -> None:
        request_timeout = timedelta(minutes=2)

        Client(config=ClientConfig(request_timeout=request_timeout))

        mock_transport.assert_called_once_with(
            "https://app.flow.bio/api",
            connection_retries=3,
            request_timeout=request_timeout,
        )


class TestClientGetRaw:

    @respx.mock
    def test_returns_raw_body_for_path(self) -> None:
        body = '{"count": 0, "samples": []}'
        respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(200, text=body),
        )

        assert Client().get_raw("/samples/search") == body

    @respx.mock
    def test_forwards_params_as_repeatable_pairs(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(200, text="{}"),
        )
        params = [("sample_types", "rna"), ("sample_types", "atac")]

        Client().get_raw("/samples/search", params=params)

        assert sorted(route.calls[0].request.url.params.multi_items()) == sorted(params)
