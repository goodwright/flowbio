import json
from http import HTTPStatus

import httpx
import pytest
import respx

from flowbio.cli import _auth
from tests.unit.cli.conftest import DEFAULT_BASE_URL

TOKEN = "test.token"


@pytest.fixture
def no_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_auth, "DEFAULT_TOKEN_FILE", _auth.Path("/nonexistent/api-token"))
    monkeypatch.delenv("FLOW_API_TOKEN", raising=False)
    monkeypatch.delenv("FLOW_TOKEN_FILE", raising=False)


class TestApiGet:

    @respx.mock
    def test_writes_raw_body_to_stdout_verbatim(self, run_cli) -> None:
        body = '{"count": 2, "pipelines": ["a", "b"]}'
        respx.get(f"{DEFAULT_BASE_URL}/pipelines").mock(
            return_value=httpx.Response(HTTPStatus.OK, text=body),
        )

        result = run_cli("api", "get", "/pipelines", "--token", TOKEN)

        assert result.exit_code == 0
        assert result.stdout == body

    @respx.mock
    def test_leading_slash_is_optional(self, run_cli) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/types").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="[]"),
        )

        result = run_cli("api", "get", "samples/types", "--token", TOKEN)

        assert result.exit_code == 0
        assert route.called

    @respx.mock
    def test_params_are_url_encoded(self, run_cli) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )

        run_cli(
            "api", "get", "/samples/search",
            "--param", "name=rna seq", "--param", "count=100",
            "--token", TOKEN,
        )

        params = route.calls[0].request.url.params
        assert params.get("name") == "rna seq"
        assert params.get("count") == "100"

    @respx.mock
    def test_repeated_param_key_is_preserved(self, run_cli) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )

        run_cli(
            "api", "get", "/samples/search",
            "--param", "sample_types=rna", "--param", "sample_types=atac",
            "--token", TOKEN,
        )

        items = route.calls[0].request.url.params.multi_items()
        assert ("sample_types", "rna") in items
        assert ("sample_types", "atac") in items

    @respx.mock
    def test_reads_anonymously_when_no_token(self, run_cli, no_credentials) -> None:
        body = '{"count": 3}'
        route = respx.get(f"{DEFAULT_BASE_URL}/pipelines").mock(
            return_value=httpx.Response(HTTPStatus.OK, text=body),
        )

        result = run_cli("api", "get", "/pipelines")

        assert result.exit_code == 0
        assert result.stdout == body
        assert "authorization" not in route.calls[0].request.headers

    @respx.mock
    def test_sends_bearer_token(self, run_cli) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )

        run_cli("api", "get", "/me", "--token", TOKEN)

        assert route.calls[0].request.headers["Authorization"] == f"Bearer {TOKEN}"

    def test_question_mark_in_path_is_usage_error(self, run_cli) -> None:
        result = run_cli(
            "api", "get", "/samples/search?name=x", "--token", TOKEN, "--json",
        )

        assert result.exit_code == 2
        assert result.stdout == ""
        assert "--param" in json.loads(result.stderr)["message"]

    def test_param_without_equals_is_usage_error(self, run_cli) -> None:
        result = run_cli(
            "api", "get", "/pipelines", "--param", "broken", "--token", TOKEN,
            "--json",
        )

        assert result.exit_code == 2
        assert result.stdout == ""
        assert "message" in json.loads(result.stderr)

    @respx.mock
    def test_not_found_maps_to_exit_code_and_json_envelope(self, run_cli) -> None:
        error_message = "No such pipeline"
        respx.get(f"{DEFAULT_BASE_URL}/pipelines/999").mock(
            return_value=httpx.Response(
                HTTPStatus.NOT_FOUND, json={"error": error_message},
            ),
        )

        result = run_cli(
            "api", "get", "/pipelines/999", "--token", TOKEN, "--json",
        )

        assert result.exit_code == 4
        assert result.stdout == ""
        document = json.loads(result.stderr)
        assert document["message"] == error_message
        assert document["status_code"] == int(HTTPStatus.NOT_FOUND)
