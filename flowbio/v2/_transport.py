from http import HTTPStatus
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


class HttpTransport:
    """Low-level HTTP transport for the Flow API.

    Wraps an ``httpx.Client`` and handles base URL management, default
    headers (User-Agent, Authorization), and error mapping from HTTP
    status codes to typed exceptions.

    :param base_url: The base URL of the Flow API
        (e.g. ``"https://app.flow.bio/api"``).
    :param connection_retries: Number of retries on connection failure.
        Only retries ``ConnectError``/``ConnectTimeout`` (TCP never
        established), so it is safe for all HTTP methods. Defaults to ``3``.
    """

    def __init__(self, base_url: str, connection_retries: int = 3) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={"User-Agent": f"flowbio-python/{_CLIENT_VERSION}"},
            transport=httpx.HTTPTransport(retries=connection_retries),
        )

    _STATUS_TO_EXCEPTION: dict[int, type[FlowApiError]] = {
        HTTPStatus.BAD_REQUEST: BadRequestError,
        HTTPStatus.UNAUTHORIZED: AuthenticationError,
        HTTPStatus.NOT_FOUND: NotFoundError,
    }

    def _raise_for_error(self, response: httpx.Response) -> None:
        if response.is_success:
            return

        body = response.json()
        message = body.get("error", body)
        exception_class = self._STATUS_TO_EXCEPTION.get(
            response.status_code, FlowApiError,
        )
        raise exception_class(response.status_code, message)

    def _handle_response(self, response: httpx.Response) -> dict:
        self._raise_for_error(response)
        return response.json()

    def _url(self, path: str) -> str:
        clean_path = path.lstrip("/")
        return f"{self._base_url}/{clean_path}"

    def get(self, path: str, params: dict | None = None) -> dict:
        """Send a GET request to the API.

        :param path: The API path to request (e.g. ``"me"`` or ``"/me"``).
        :param params: Optional query parameters to include in the request.
        :returns: The parsed JSON response body.
        :raises FlowApiError: If the API returns a non-success status code.
        """
        response = self._client.get(self._url(path), params=params)
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
        response = self._client.get(self._url(path), params=params)
        self._raise_for_error(response)
        return response.content

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
            (e.g. ``{"file": ("name.txt", bytes, "text/plain")}``).
        :returns: The parsed JSON response body.
        :raises FlowApiError: If the API returns a non-success status code.
        """
        response = self._client.post(
            self._url(path), json=json, data=data, files=files,
        )
        return self._handle_response(response)

    def set_token(self, token: str) -> None:
        """Set the Bearer token for subsequent requests.

        :param token: The JWT access token.
        """
        self._client.headers["Authorization"] = f"Bearer {token}"
