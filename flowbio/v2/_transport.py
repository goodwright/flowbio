from datetime import timedelta
from http import HTTPMethod, HTTPStatus
from importlib.metadata import PackageNotFoundError, version

import httpx

from flowbio.v2.exceptions import (
    AuthenticationError,
    BadRequestError,
    FlowApiError,
    NotFoundError,
)

try:
    _CLIENT_VERSION = version("flowbio")
except PackageNotFoundError:
    _CLIENT_VERSION = "unknown"


class _RefreshFailed(Exception):
    """Internal signal that GET /token did not yield a usable access token."""


class HttpTransport:
    """Low-level HTTP transport for the Flow API.

    Wraps an ``httpx.Client`` and handles base URL management, default
    headers (User-Agent, Authorization), and error mapping from HTTP
    status codes to typed exceptions.

    On a 401 response from a request that carried a Bearer token, the
    transport automatically calls ``GET /token`` to mint a fresh access
    JWT (using the ``flow_refresh_token`` cookie set by ``/login``) and
    retries the original request once. If the refresh fails, the
    original 401 surfaces unchanged.

    :param base_url: The base URL of the Flow API
        (e.g. ``"https://app.flow.bio/api"``).
    :param connection_retries: Number of retries on connection failure.
        Only retries ``ConnectError``/``ConnectTimeout`` (TCP never
        established), so it is safe for all HTTP methods. Defaults to ``3``.
    :param request_timeout: Per-request timeout for read, write, and
        pool acquisition. Defaults to ``timedelta(seconds=60)``. Connect
        timeout is fixed at 10 s independently — TCP handshake is bounded
        by DNS/network, not by how long the API takes to respond. httpx's
        own default of 5 s for read is too short for upload chunks
        against a busy backend.
    """

    _CONNECT_TIMEOUT_SECONDS = 10.0

    def __init__(
        self,
        base_url: str,
        connection_retries: int = 3,
        request_timeout: timedelta = timedelta(seconds=60),
    ) -> None:
        self._base_url = base_url.rstrip("/")
        request_seconds = request_timeout.total_seconds()
        self._client = httpx.Client(
            headers={"User-Agent": f"flowbio-python/{_CLIENT_VERSION}"},
            transport=httpx.HTTPTransport(retries=connection_retries),
            timeout=httpx.Timeout(
                connect=self._CONNECT_TIMEOUT_SECONDS,
                read=request_seconds,
                write=request_seconds,
                pool=request_seconds,
            ),
        )

    _STATUS_TO_EXCEPTION: dict[int, type[FlowApiError]] = {
        HTTPStatus.BAD_REQUEST: BadRequestError,
        HTTPStatus.UNAUTHORIZED: AuthenticationError,
        HTTPStatus.NOT_FOUND: NotFoundError,
    }

    def _raise_for_error(self, response: httpx.Response) -> None:
        if response.is_success:
            return

        try:
            body = response.json()
        except ValueError:
            # Upstream proxies (Cloudflare, GCP load balancers, nginx) return
            # HTML/plain-text on 5xx instead of the API's JSON envelope.
            message = self._non_json_error_message(response)
        else:
            message = body.get("error", body)
        exception_class = self._STATUS_TO_EXCEPTION.get(
            response.status_code, FlowApiError,
        )
        raise exception_class(response.status_code, message)

    @staticmethod
    def _non_json_error_message(response: httpx.Response) -> str:
        base = f"HTTP {response.status_code} {response.reason_phrase}"
        body_text = response.text.strip()
        if not body_text:
            return base
        snippet = body_text[:500]
        if len(body_text) > 500:
            snippet += "..."
        return f"{base}: {snippet}"

    def _handle_response(self, response: httpx.Response) -> dict:
        self._raise_for_error(response)
        return response.json()

    def _url(self, path: str) -> str:
        clean_path = path.lstrip("/")
        return f"{self._base_url}/{clean_path}"

    def _request(self, method: HTTPMethod, url: str, **kwargs) -> httpx.Response:
        response = self._client.request(method, url, **kwargs)
        needs_access_token_refresh = response.status_code == HTTPStatus.UNAUTHORIZED and self._can_refresh()
        if needs_access_token_refresh:
            try:
                self._refresh_access_token()
                return self._client.request(method, url, **kwargs)
            except _RefreshFailed:
                pass

        return response

    def _can_refresh(self) -> bool:
        return "Authorization" in self._client.headers

    def _refresh_access_token(self) -> None:
        # Calls httpx directly (not self._request) to avoid recursion.
        # The refresh cookie travels via the httpx cookie jar.
        response = self._client.get(self._url("/token"))
        if not response.is_success:
            raise _RefreshFailed
        try:
            new_token = response.json().get("token")
        except (ValueError, AttributeError) as e:
            # ValueError: body is not JSON (e.g. proxy returned HTML).
            # AttributeError: body is JSON but not a dict (e.g. list, null).
            raise _RefreshFailed from e
        if not new_token:
            raise _RefreshFailed
        self.set_token(new_token)

    def get(self, path: str, params: dict | None = None) -> dict:
        """Send a GET request to the API.

        :param path: The API path to request (e.g. ``"me"`` or ``"/me"``).
        :param params: Optional query parameters to include in the request.
        :returns: The parsed JSON response body.
        :raises FlowApiError: If the API returns a non-success status code.
        """
        response = self._request(HTTPMethod.GET, self._url(path), params=params)
        return self._handle_response(response)

    def get_bytes(self, path: str, params: dict | None = None) -> bytes:
        """Send a GET request and return the raw response bytes.

        Use this for endpoints that return binary content (e.g. file
        downloads) instead of JSON.

        :param path: The API path to request.
        :param params: Optional query parameters to include in the request.
        :returns: The raw response bytes.
        :raises FlowApiError: If the API returns a non-success status code.
        """
        response = self._request(HTTPMethod.GET, self._url(path), params=params)
        self._raise_for_error(response)
        return response.content

    def get_text(
        self, path: str, params: list[tuple[str, str]] | None = None,
    ) -> str:
        """Send a GET request and return the raw response body as text.

        Unlike :meth:`get`, the body is returned undecoded from JSON so
        callers can pass it through verbatim.

        :param path: The API path to request.
        :param params: Optional query parameters, as key/value pairs so a
            key may repeat (e.g. multiple ``sample_types`` filters).
        :returns: The response body text.
        :raises FlowApiError: If the API returns a non-success status code.
        """
        response = self._request(HTTPMethod.GET, self._url(path), params=params)
        self._raise_for_error(response)
        return response.text

    def post(
        self,
        path: str,
        json: dict | None = None,
        data: dict | None = None,
        files: dict | None = None,
    ) -> dict:
        """Send a POST request to the API.

        Use ``json`` for JSON-encoded bodies, or ``data``/``files`` for
        multipart form data.

        :param path: The API path to request (e.g. ``"login"`` or ``"/login"``).
        :param json: Optional JSON body to send with the request.
        :param data: Optional form fields for multipart requests.
        :param files: Optional file fields for multipart requests,
            following the httpx file format
            (e.g. ``{"file": ("name.txt", bytes, "text/plain")}``). File
            contents must be ``bytes``, not a file handle, so the request
            can be retried after a token refresh without exhausting the
            stream.
        :returns: The parsed JSON response body.
        :raises FlowApiError: If the API returns a non-success status code.
        """
        response = self._request(
            HTTPMethod.POST, self._url(path), json=json, data=data, files=files,
        )
        return self._handle_response(response)

    def set_token(self, token: str) -> None:
        """Set the Bearer token for subsequent requests.

        :param token: The JWT access token.
        """
        self._client.headers["Authorization"] = f"Bearer {token}"
