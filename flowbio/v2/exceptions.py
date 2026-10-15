"""
Exceptions raised by the v2 client.

All exceptions inherit from :class:`FlowApiError`, which carries the
HTTP status code and error message from the response.
"""

from http import HTTPStatus


class FlowApiError(Exception):
    """Base exception for all Flow API errors.

    Raised when the API returns a non-success HTTP response. Carries the
    status code and error message from the response body.

    :param status_code: The HTTP status code from the response.
    :param message: The error message — either a string or a dict of
        field-level errors (e.g. ``{"field": ["error message"]}``).
    :param details: Optional per-location problems behind the error. From a
        Problem Details body, each is a ``{"pointer" | "parameter", "code",
        "detail"}`` dict, where ``pointer`` is a JSON Pointer into the request
        body and ``parameter`` names a query or path parameter. A legacy
        endpoint's error envelope gives ``{"field", "code", "message"}`` dicts
        instead. ``None`` when the response names no locations.
    :param code: The stable machine-readable kind of problem (e.g.
        ``"validation_error"``, ``"not_found"``) from a Problem Details body,
        for branching on instead of the message text. ``None`` when the
        response is not a problem. Treat an unrecognised code as the generic
        error for its status.

    Example::

        try:
            client.samples.get("missing")
        except FlowApiError as error:
            if error.code == "not_found":
                ...
    """

    def __init__(
        self,
        status_code: int,
        message: str | dict[str, list[str]],
        details: list[dict] | None = None,
        code: str | None = None,
    ) -> None:
        self.status_code = status_code
        self.message = message
        self.details = details
        self.code = code
        super().__init__(str(message))


class AuthenticationError(FlowApiError):
    """Raised when the API returns a 401 Unauthorized response."""

    pass


class BadRequestError(FlowApiError):
    """Raised when the API returns a 400 Bad Request response."""

    pass


class AnnotationValidationError(BadRequestError):
    """Raised when the annotation upload in :meth:`~flowbio.v2.samples.SampleResource.upload_multiplexed_data` returns hard validation errors, or when annotation upload is told not to
    ignore warnings.

    The annotation endpoint returns ``{"validation": [...]}`` with status 400
    for errors that cannot be ignored (as opposed to warnings which can, unless they are not configured to be ignored).

    :param errors: List of validation error dicts from the response.
    """

    def __init__(self, errors: list[dict]) -> None:
        self.errors = errors
        super().__init__(
            HTTPStatus.BAD_REQUEST,
            f"Annotation has {len(errors)} validation error(s)",
        )


class NotFoundError(FlowApiError):
    """Raised when the API returns a 404 Not Found response."""

    pass
