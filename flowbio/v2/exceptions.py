"""
Exceptions raised by the v2 client.

All exceptions inherit from :class:`FlowApiError`, which carries the
HTTP status code and error message from the response.
"""


class FlowApiError(Exception):
    """Base exception for all Flow API errors.

    Raised when the API returns a non-success HTTP response. Carries the
    status code and error message from the response body.

    :param status_code: The HTTP status code from the response.
    :param message: The error message — either a string or a dict of
        field-level errors (e.g. ``{"field": ["error message"]}``).
    """

    def __init__(self, status_code: int, message: str | dict[str, list[str]]) -> None:
        self.status_code = status_code
        self.message = message
        super().__init__(str(message))


class AuthenticationError(FlowApiError):
    """Raised when the API returns a 401 Unauthorized response."""

    pass


class BadRequestError(FlowApiError):
    """Raised when the API returns a 400 Bad Request response."""

    pass


class NotFoundError(FlowApiError):
    """Raised when the API returns a 404 Not Found response."""

    pass
