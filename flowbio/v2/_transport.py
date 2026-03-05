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
    """

    def __init__(self, base_url: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._client = httpx.Client(
            headers={"User-Agent": f"flowbio-python/{_CLIENT_VERSION}"},
        )

    _STATUS_TO_EXCEPTION: dict[int, type[FlowApiError]] = {
        400: BadRequestError,
        401: AuthenticationError,
        404: NotFoundError,
    }

    def _handle_response(self, response: httpx.Response) -> dict:
        if response.is_success:
            return response.json()

        body = response.json()
        message = body.get("error", "Unknown error")
        exception_class = self._STATUS_TO_EXCEPTION.get(
            response.status_code, FlowApiError,
        )
        raise exception_class(response.status_code, message)

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

    def post(self, path: str, json: dict | None = None) -> dict:
        """Send a POST request to the API.

        :param path: The API path to request (e.g. ``"login"`` or ``"/login"``).
        :param json: Optional JSON body to send with the request.
        :returns: The parsed JSON response body.
        :raises FlowApiError: If the API returns a non-success status code.
        """
        response = self._client.post(self._url(path), json=json)
        return self._handle_response(response)

    def set_token(self, token: str) -> None:
        """Set the Bearer token for subsequent requests.

        :param token: The JWT access token.
        """
        self._client.headers["Authorization"] = f"Bearer {token}"
