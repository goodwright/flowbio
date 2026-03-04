from flowbio.v2.exceptions import (
    AuthenticationError,
    BadRequestError,
    FlowApiError,
    NotFoundError,
)


class TestFlowApiError:

    def test_stores_status_code_and_message(self):
        status_code = 400
        message = "Something went wrong"

        error = FlowApiError(status_code, message)

        assert error.status_code == status_code
        assert error.message == message

    def test_str_returns_message(self):
        message = "Something went wrong"

        error = FlowApiError(400, message)

        assert str(error) == message

    def test_stores_dict_message(self):
        message = {"username": ["This field is required."]}

        error = FlowApiError(400, message)

        assert error.message == message

    def test_str_includes_field_name_for_dict_message(self):
        message = {"username": ["This field is required."]}

        error = FlowApiError(400, message)

        assert "username" in str(error)


class TestAuthenticationError:

    def test_is_flow_api_error(self) -> None:
        error = AuthenticationError(401, "Unauthorized")

        assert isinstance(error, FlowApiError)

    def test_stores_status_code_and_message(self) -> None:
        status_code = 401
        message = "Unauthorized"

        error = AuthenticationError(status_code, message)

        assert error.status_code == status_code
        assert error.message == message


class TestBadRequestError:

    def test_is_flow_api_error(self) -> None:
        error = BadRequestError(400, "Invalid credentials")

        assert isinstance(error, FlowApiError)

    def test_stores_status_code_and_message(self) -> None:
        status_code = 400
        message = "Invalid credentials"

        error = BadRequestError(status_code, message)

        assert error.status_code == status_code
        assert error.message == message


class TestNotFoundError:

    def test_is_flow_api_error(self) -> None:
        error = NotFoundError(404, "Not found")

        assert isinstance(error, FlowApiError)

    def test_stores_status_code_and_message(self) -> None:
        status_code = 404
        message = "Not found"

        error = NotFoundError(status_code, message)

        assert error.status_code == status_code
        assert error.message == message
