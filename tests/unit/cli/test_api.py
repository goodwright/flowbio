import io
import json
from http import HTTPStatus

import httpx
import pytest
import respx

from flowbio.cli import _auth
from tests.unit.cli.conftest import DEFAULT_BASE_URL
from tests.unit.v2.conftest import problem_response

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
    def test_param_with_empty_value_is_sent(self, run_cli) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )

        result = run_cli(
            "api", "get", "/samples/search", "--param", "name=", "--token", TOKEN,
        )

        assert result.exit_code == 0
        assert route.calls[0].request.url.params.get("name") == ""

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

    @respx.mock
    def test_problem_error_is_nested_in_json_error_document(self, run_cli) -> None:
        response = problem_response(
            HTTPStatus.NOT_FOUND, "not_found", "pipeline 999 does not exist",
        )
        problem = response.json()
        respx.get(f"{DEFAULT_BASE_URL}/v2/pipelines/999").mock(return_value=response)

        result = run_cli(
            "api", "get", "/v2/pipelines/999", "--token", TOKEN, "--json",
        )

        assert result.exit_code == 4
        assert json.loads(result.stderr) == {
            "message": problem["detail"],
            "status_code": int(HTTPStatus.NOT_FOUND),
            "problem": problem,
        }


WRITE_VERBS = pytest.mark.parametrize(
    ("verb", "route_for"), [("post", respx.post), ("patch", respx.patch)],
)


class TestApiWrite:

    @WRITE_VERBS
    @respx.mock
    def test_sends_body_file_and_writes_raw_response(
        self, run_cli, tmp_path, verb, route_for,
    ) -> None:
        body = '{"name": "x"}'
        response_body = '{"id": "1", "name": "x"}'
        body_file = tmp_path / "body.json"
        body_file.write_text(body)
        route = route_for(f"{DEFAULT_BASE_URL}/v2/projects/1").mock(
            return_value=httpx.Response(HTTPStatus.OK, text=response_body),
        )

        result = run_cli(
            "api", verb, "/v2/projects/1", "--body", str(body_file),
            "--token", TOKEN,
        )

        assert result.exit_code == 0
        assert result.stdout == response_body
        request = route.calls[0].request
        assert request.content == body.encode()
        assert request.headers["Authorization"] == f"Bearer {TOKEN}"

    @WRITE_VERBS
    @respx.mock
    def test_reads_body_from_stdin(
        self, run_cli, monkeypatch, verb, route_for,
    ) -> None:
        body = '{"metadata": {"condition": null}}'
        monkeypatch.setattr("sys.stdin", io.StringIO(body))
        route = route_for(f"{DEFAULT_BASE_URL}/v2/samples/1").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )

        result = run_cli(
            "api", verb, "/v2/samples/1", "--body", "-", "--token", TOKEN,
        )

        assert result.exit_code == 0
        assert route.calls[0].request.content == body.encode()

    @respx.mock
    def test_post_writes_created_body_to_stdout(self, run_cli, tmp_path) -> None:
        response_body = '{"id": "7", "name": "RNA-seq 2026"}'
        body_file = tmp_path / "body.json"
        body_file.write_text('{"name": "RNA-seq 2026"}')
        respx.post(f"{DEFAULT_BASE_URL}/v2/projects").mock(
            return_value=httpx.Response(HTTPStatus.CREATED, text=response_body),
        )

        result = run_cli(
            "api", "post", "/v2/projects", "--body", str(body_file),
            "--token", TOKEN,
        )

        assert result.exit_code == 0
        assert result.stdout == response_body

    @respx.mock
    def test_missing_body_file_is_usage_error(self, run_cli, tmp_path) -> None:
        missing = tmp_path / "missing.json"
        route = respx.patch(f"{DEFAULT_BASE_URL}/v2/samples/1").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )

        result = run_cli(
            "api", "patch", "/v2/samples/1", "--body", str(missing),
            "--token", TOKEN, "--json",
        )

        assert result.exit_code == 2
        assert result.stdout == ""
        assert str(missing) in json.loads(result.stderr)["message"]
        assert not route.called

    def test_body_is_required(self, run_cli) -> None:
        result = run_cli("api", "patch", "/v2/samples/1", "--token", TOKEN)

        assert result.exit_code == 2

    @respx.mock
    def test_requires_credentials(
        self, run_cli, no_credentials, monkeypatch, tmp_path,
    ) -> None:
        body_file = tmp_path / "body.json"
        body_file.write_text('{"name": "x"}')
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        route = respx.post(f"{DEFAULT_BASE_URL}/v2/projects").mock(
            return_value=httpx.Response(HTTPStatus.CREATED, text="{}"),
        )

        result = run_cli("api", "post", "/v2/projects", "--body", str(body_file))

        assert result.exit_code == 2
        assert not route.called

    @respx.mock
    def test_validation_problem_is_passed_through(self, run_cli, tmp_path) -> None:
        body_file = tmp_path / "body.json"
        body_file.write_text('{"project": "2"}')
        response = problem_response(
            HTTPStatus.UNPROCESSABLE_ENTITY,
            "validation_error",
            "`project` can't be changed with this endpoint: moving a sample "
            "changes who can see it and its data. Move it in the Flow web app.",
        )
        problem = response.json()
        respx.patch(f"{DEFAULT_BASE_URL}/v2/samples/1").mock(return_value=response)

        result = run_cli(
            "api", "patch", "/v2/samples/1", "--body", str(body_file),
            "--token", TOKEN, "--json",
        )

        assert result.exit_code == 5
        assert result.stdout == ""
        assert json.loads(result.stderr) == {
            "message": problem["detail"],
            "status_code": int(HTTPStatus.UNPROCESSABLE_ENTITY),
            "problem": problem,
        }

    def test_there_is_no_delete_verb(self, run_cli) -> None:
        result = run_cli("api", "delete", "/v2/projects/1", "--token", TOKEN)

        assert result.exit_code == 2
