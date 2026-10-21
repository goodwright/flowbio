import json
import threading
from collections.abc import Iterator
from datetime import timedelta
from http import HTTPMethod, HTTPStatus
from http.server import BaseHTTPRequestHandler, HTTPServer
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
    UnprocessableError,
)

from tests.unit.v2.conftest import DEFAULT_BASE_URL, problem_response


class TestTransportConnectionRetries:

    @respx.mock
    @patch("time.sleep")
    def test_succeeds_after_as_many_connection_failures_as_retries(self, _mock_sleep) -> None:
        connection_retries = 2
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(side_effect=[
            httpx.ConnectError("refused"),
            httpx.ConnectError("refused"),
            httpx.Response(HTTPStatus.OK, json={"id": 1}),
        ])
        transport = HttpTransport(DEFAULT_BASE_URL, connection_retries=connection_retries)

        result = transport.get("/me")

        assert result == {"id": 1}
        assert route.call_count == connection_retries + 1

    @respx.mock
    @patch("time.sleep")
    def test_raises_after_one_more_connection_failure_than_retries(self, _mock_sleep) -> None:
        connection_retries = 2
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            side_effect=httpx.ConnectError("refused"),
        )
        transport = HttpTransport(DEFAULT_BASE_URL, connection_retries=connection_retries)

        with pytest.raises(httpx.ConnectError):
            transport.get("/me")

        assert route.call_count == connection_retries + 1

    @respx.mock
    @patch("time.sleep")
    def test_retries_three_times_by_default(self, _mock_sleep) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            side_effect=httpx.ConnectError("refused"),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(httpx.ConnectError):
            transport.get("/me")

        assert route.call_count == 4

    @respx.mock
    @patch("time.sleep")
    def test_retries_a_connect_timeout(self, _mock_sleep) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(side_effect=[
            httpx.ConnectTimeout("timed out"),
            httpx.Response(HTTPStatus.OK, json={}),
        ])
        transport = HttpTransport(DEFAULT_BASE_URL)

        transport.get("/me")

        assert route.call_count == 2

    @respx.mock
    @patch("time.sleep")
    def test_does_not_retry_a_read_timeout(self, _mock_sleep) -> None:
        # The request may already have reached the server, so retrying a
        # write could apply it twice.
        route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            side_effect=httpx.ReadTimeout("timed out"),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(httpx.ReadTimeout):
            transport.get("/me")

        assert route.call_count == 1


class TestTransportRequestTimeout:

    @patch("flowbio.v2._transport.httpx.Client")
    def test_default_timeout_applies_to_read_write_pool(self, mock_client) -> None:
        HttpTransport(DEFAULT_BASE_URL)

        timeout = mock_client.call_args.kwargs["timeout"]
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.read == 60.0
        assert timeout.write == 60.0
        assert timeout.pool == 60.0

    @patch("flowbio.v2._transport.httpx.Client")
    def test_custom_timeout_applies_to_read_write_pool(self, mock_client) -> None:
        custom_timeout = timedelta(minutes=2)

        HttpTransport(DEFAULT_BASE_URL, request_timeout=custom_timeout)

        timeout = mock_client.call_args.kwargs["timeout"]
        assert isinstance(timeout, httpx.Timeout)
        assert timeout.read == custom_timeout.total_seconds()
        assert timeout.write == custom_timeout.total_seconds()
        assert timeout.pool == custom_timeout.total_seconds()

    @patch("flowbio.v2._transport.httpx.Client")
    def test_connect_timeout_is_independent_of_request_timeout(self, mock_client) -> None:
        # Connect time is bounded by DNS + TCP handshake, so a long
        # request_timeout shouldn't bleed into how long we wait for a
        # connection that's not coming.
        HttpTransport(DEFAULT_BASE_URL, request_timeout=timedelta(minutes=10))

        timeout = mock_client.call_args.kwargs["timeout"]
        assert timeout.connect == 10.0


class _RecordingHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        self.server.request_targets.append(self.path)
        body = b"{}"
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args) -> None:
        pass


@pytest.fixture
def local_server() -> Iterator[HTTPServer]:
    server = HTTPServer(("127.0.0.1", 0), _RecordingHandler)
    server.request_targets = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield server
    server.shutdown()
    server.server_close()


@pytest.fixture
def proxy_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in ("HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY"):
        monkeypatch.delenv(name, raising=False)
        monkeypatch.delenv(name.lower(), raising=False)
    return monkeypatch


class TestTransportProxy:

    def test_routes_requests_through_the_environment_proxy(
        self, local_server: HTTPServer, proxy_env: pytest.MonkeyPatch,
    ) -> None:
        host, port = local_server.server_address
        proxy_env.setenv("HTTP_PROXY", f"http://{host}:{port}")
        transport = HttpTransport("http://flow.invalid/api")

        transport.get("/me")

        # A forward proxy receives the absolute target URL; an origin server
        # receives only the path.
        assert local_server.request_targets == ["http://flow.invalid/api/me"]


    def test_connects_directly_to_a_host_exempted_by_no_proxy(
        self, local_server: HTTPServer, proxy_env: pytest.MonkeyPatch,
    ) -> None:
        host, port = local_server.server_address
        proxy_env.setenv("HTTP_PROXY", "http://127.0.0.1:9")
        proxy_env.setenv("NO_PROXY", host)
        transport = HttpTransport(f"http://{host}:{port}/api", connection_retries=0)

        transport.get("/me")

        assert local_server.request_targets == ["/api/me"]

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


class TestTransportProblemDetails:

    @respx.mock
    def test_raises_unprocessable_error_on_422(self) -> None:
        respx.post(f"{DEFAULT_BASE_URL}/v2/projects").mock(
            return_value=problem_response(
                HTTPStatus.UNPROCESSABLE_ENTITY, "validation_error", "Invalid project",
                [{"pointer": "/name", "code": "invalid", "detail": "You already have a project with this name."}],
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(UnprocessableError) as exc_info:
            transport.post("/v2/projects", json={"name": "Atlas"})

        # A caller handling invalid input as a bad request keeps doing so.
        assert isinstance(exc_info.value, BadRequestError)
        assert exc_info.value.code == "validation_error"
        assert exc_info.value.details == [
            {"pointer": "/name", "code": "invalid", "detail": "You already have a project with this name."},
        ]

    @respx.mock
    def test_an_unmapped_client_error_is_not_a_bad_request(self) -> None:
        respx.post(f"{DEFAULT_BASE_URL}/v2/projects").mock(
            return_value=problem_response(HTTPStatus.CONFLICT, "conflict", "Conflict"),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(FlowApiError) as exc_info:
            transport.post("/v2/projects", json={})

        assert not isinstance(exc_info.value, BadRequestError)

    @respx.mock
    def test_reads_message_code_and_details_from_problem(self) -> None:
        detail = "Invalid sample import request"
        code = "validation_error"
        errors = [
            {"pointer": "/imports/0/accession", "code": "invalid", "detail": "bad accession"},
            {"parameter": "page", "code": "greater_than_equal", "detail": "too small"},
        ]
        respx.post(f"{DEFAULT_BASE_URL}/samples/imports").mock(
            return_value=problem_response(
                HTTPStatus.UNPROCESSABLE_ENTITY, code, detail, errors,
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(FlowApiError) as exc_info:
            transport.post("/samples/imports", json={})

        assert exc_info.value.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
        assert exc_info.value.message == detail
        assert exc_info.value.code == code
        assert exc_info.value.details == errors

    @respx.mock
    def test_keeps_problem_body_as_sent(self) -> None:
        response = problem_response(
            HTTPStatus.INTERNAL_SERVER_ERROR, "internal_error", "Internal error",
        )
        problem = response.json()
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(return_value=response)

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(FlowApiError) as exc_info:
            transport.get("/me")

        assert exc_info.value.problem == problem

    @respx.mock
    def test_problem_with_no_errors_has_no_details(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/samples/imports/999").mock(
            return_value=problem_response(
                HTTPStatus.NOT_FOUND, "not_found", "sample import 999 does not exist",
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(NotFoundError) as exc_info:
            transport.get("/samples/imports/999")

        assert exc_info.value.details is None

    @respx.mock
    def test_401_problem_raises_authentication_error(self) -> None:
        detail = "Token has expired"
        code = "unauthenticated"
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=problem_response(HTTPStatus.UNAUTHORIZED, code, detail),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(AuthenticationError) as exc_info:
            transport.get("/me")

        assert exc_info.value.message == detail
        assert exc_info.value.code == code

    @respx.mock
    def test_problem_without_flow_members_falls_back_to_title(self) -> None:
        title = "Service Unavailable"
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(
                HTTPStatus.SERVICE_UNAVAILABLE,
                headers={"Content-Type": "application/problem+json"},
                json={"type": "about:blank", "title": title, "status": 503},
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(FlowApiError) as exc_info:
            transport.get("/me")

        assert exc_info.value.status_code == HTTPStatus.SERVICE_UNAVAILABLE
        assert exc_info.value.message == title
        assert exc_info.value.code is None
        assert exc_info.value.details is None

    @respx.mock
    def test_problem_without_detail_or_title_keeps_body_as_message(self) -> None:
        body = {"status": 502}
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(
                HTTPStatus.BAD_GATEWAY,
                headers={"Content-Type": "application/problem+json"},
                json=body,
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(FlowApiError) as exc_info:
            transport.get("/me")

        assert exc_info.value.message == body

    @respx.mock
    def test_json_body_with_problem_members_is_not_read_as_problem(self) -> None:
        body = {"detail": "looks like a problem", "code": "validation_error"}
        respx.get(f"{DEFAULT_BASE_URL}/legacy").mock(
            return_value=httpx.Response(HTTPStatus.BAD_REQUEST, json=body),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(BadRequestError) as exc_info:
            transport.get("/legacy")

        assert exc_info.value.message == body
        assert exc_info.value.code is None
        assert exc_info.value.problem is None

    @respx.mock
    def test_legacy_envelope_is_unwrapped_to_message_and_details(self) -> None:
        message = "Invalid page"
        details = [{"field": "page", "code": "invalid", "message": "must be positive"}]
        respx.get(f"{DEFAULT_BASE_URL}/legacy").mock(
            return_value=httpx.Response(
                HTTPStatus.UNPROCESSABLE_ENTITY,
                json={"error": {"code": "validation_error", "message": message, "details": details}},
            ),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(UnprocessableError) as exc_info:
            transport.get("/legacy")

        assert exc_info.value.message == message
        assert exc_info.value.details == details


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


class TestTransportGetText:

    @respx.mock
    def test_returns_raw_response_body_verbatim(self) -> None:
        body = '{"count": 2, "pipelines": [1, 2]}'
        respx.get(f"{DEFAULT_BASE_URL}/pipelines").mock(
            return_value=httpx.Response(HTTPStatus.OK, text=body),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        assert transport.get_text("/pipelines") == body

    @respx.mock
    def test_encodes_params_into_query_string(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/samples/search").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        transport.get_text("/samples/search", params=[("name", "rna seq")])

        assert route.calls[0].request.url.params.get("name") == "rna seq"

    @respx.mock
    def test_raises_flow_api_error_on_non_success(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/nope").mock(
            return_value=httpx.Response(
                HTTPStatus.NOT_FOUND, json={"error": "missing"},
            ),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(NotFoundError):
            transport.get_text("/nope")


class TestTransportSendText:

    @respx.mock
    def test_sends_body_verbatim_as_json(self) -> None:
        body = '{"name": "Ünïcode", "a": 1}'.encode()
        route = respx.patch(f"{DEFAULT_BASE_URL}/v2/samples/1").mock(
            return_value=httpx.Response(HTTPStatus.OK, text="{}"),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        transport.send_text(HTTPMethod.PATCH, "/v2/samples/1", body)

        request = route.calls[0].request
        assert request.content == body
        assert request.headers["Content-Type"] == "application/json"

    @respx.mock
    def test_returns_raw_response_body(self) -> None:
        response_body = '{"id": "1", "name": "x"}'
        respx.post(f"{DEFAULT_BASE_URL}/v2/projects").mock(
            return_value=httpx.Response(HTTPStatus.CREATED, text=response_body),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        result = transport.send_text(HTTPMethod.POST, "/v2/projects", b"{}")

        assert result == response_body

    @respx.mock
    def test_raises_flow_api_error_on_non_success(self) -> None:
        respx.patch(f"{DEFAULT_BASE_URL}/v2/projects/9").mock(
            return_value=httpx.Response(
                HTTPStatus.NOT_FOUND, json={"error": "missing"},
            ),
        )
        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(NotFoundError):
            transport.send_text(HTTPMethod.PATCH, "/v2/projects/9", b"{}")


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
    @patch("time.sleep")
    def test_retries_a_connection_failure_while_refreshing(self, _mock_sleep) -> None:
        new_token = "fresh.jwt"
        respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            side_effect=[
                httpx.Response(HTTPStatus.UNAUTHORIZED, json={"error": "Not authorized"}),
                httpx.Response(HTTPStatus.OK, json={"username": "alice"}),
            ],
        )
        respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            side_effect=[
                httpx.ConnectError("refused"),
                httpx.Response(HTTPStatus.OK, json={"token": new_token, "user": {}}),
            ],
        )
        transport = HttpTransport(DEFAULT_BASE_URL)
        transport.set_token("expired.jwt")

        result = transport.get("/me")

        assert result == {"username": "alice"}

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
    def test_anonymous_401_does_not_attempt_refresh(self) -> None:
        me_route = respx.get(f"{DEFAULT_BASE_URL}/me").mock(
            return_value=httpx.Response(401, json={"error": "Not authorized"}),
        )
        token_route = respx.get(f"{DEFAULT_BASE_URL}/token").mock(
            return_value=httpx.Response(200, json={"token": "unused.jwt", "user": {}}),
        )

        transport = HttpTransport(DEFAULT_BASE_URL)

        with pytest.raises(AuthenticationError):
            transport.get_text("/me")

        assert not token_route.called
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

