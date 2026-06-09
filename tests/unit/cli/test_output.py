import io
import json
from http import HTTPStatus

from flowbio.cli._exit_codes import CliUsageError, ExitCode, exit_code_for
from flowbio.cli._output import Output, format_issue
from flowbio.v2.exceptions import (
    AnnotationValidationError,
    AuthenticationError,
    BadRequestError,
    FlowApiError,
    NotFoundError,
)


class TestExitCodeValues:

    def test_values_match_contract(self) -> None:
        assert ExitCode.SUCCESS == 0
        assert ExitCode.RUNTIME == 1
        assert ExitCode.USAGE == 2
        assert ExitCode.AUTH == 3
        assert ExitCode.NOT_FOUND == 4
        assert ExitCode.BAD_REQUEST == 5


class TestExitCodeFor:

    def test_authentication_error_maps_to_auth(self) -> None:
        exc = AuthenticationError(HTTPStatus.UNAUTHORIZED, "Unauthenticated")

        assert exit_code_for(exc) == ExitCode.AUTH

    def test_not_found_error_maps_to_not_found(self) -> None:
        exc = NotFoundError(HTTPStatus.NOT_FOUND, "Missing")

        assert exit_code_for(exc) == ExitCode.NOT_FOUND

    def test_bad_request_error_maps_to_bad_request(self) -> None:
        exc = BadRequestError(HTTPStatus.BAD_REQUEST, "Bad data type")

        assert exit_code_for(exc) == ExitCode.BAD_REQUEST

    def test_annotation_validation_error_maps_to_bad_request(self) -> None:
        exc = AnnotationValidationError(errors=[{"row": 1, "message": "bad"}])

        assert exit_code_for(exc) == ExitCode.BAD_REQUEST

    def test_other_flow_api_error_maps_to_runtime(self) -> None:
        exc = FlowApiError(HTTPStatus.INTERNAL_SERVER_ERROR, "Server exploded")

        assert exit_code_for(exc) == ExitCode.RUNTIME

    def test_cli_usage_error_maps_to_usage(self) -> None:
        exc = CliUsageError("conflicting flags")

        assert exit_code_for(exc) == ExitCode.USAGE


class TestHumanOutput:

    def test_result_writes_single_line_to_stdout(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        output = Output(json_mode=False, stdout=out, stderr=err)

        output.emit_result("Uploaded data data_1", {"id": "data_1"})

        assert out.getvalue() == "Uploaded data data_1\n"
        assert err.getvalue() == ""

    def test_advisory_goes_to_stderr_only(self) -> None:
        advisory = "Required columns: name, reads1"
        out, err = io.StringIO(), io.StringIO()
        output = Output(json_mode=False, stdout=out, stderr=err)

        output.emit_advisory(advisory)

        assert out.getvalue() == ""
        assert err.getvalue() == f"{advisory}\n"

    def test_error_goes_to_stderr_only(self) -> None:
        message = "something failed"
        out, err = io.StringIO(), io.StringIO()
        output = Output(json_mode=False, stdout=out, stderr=err)

        output.emit_error(message, status_code=HTTPStatus.BAD_REQUEST)

        assert out.getvalue() == ""
        assert message in err.getvalue()

    def test_error_renders_details_one_per_line_after_summary(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        output = Output(json_mode=False, stdout=out, stderr=err)

        output.emit_error(
            "Annotation has 2 validation error(s)",
            status_code=HTTPStatus.BAD_REQUEST,
            details=[
                {"row": 1, "message": "Invalid scientist"},
                {"row": 3, "message": "Unknown organism"},
            ],
        )

        lines = err.getvalue().splitlines()
        assert lines[0] == "Error: Annotation has 2 validation error(s)"
        assert "row 1: Invalid scientist" in lines[1]
        assert "row 3: Unknown organism" in lines[2]
        assert out.getvalue() == ""


class TestJsonOutput:

    def test_result_writes_exactly_one_document_to_stdout(self) -> None:
        document = {"id": "data_1"}
        out, err = io.StringIO(), io.StringIO()
        output = Output(json_mode=True, stdout=out, stderr=err)

        output.emit_result("ignored human line", document)

        assert json.loads(out.getvalue()) == document
        assert out.getvalue().count("\n") == 1
        assert err.getvalue() == ""

    def test_advisory_is_suppressed_from_stdout(self) -> None:
        out, err = io.StringIO(), io.StringIO()
        output = Output(json_mode=True, stdout=out, stderr=err)

        output.emit_advisory("Required columns: name, reads1")

        assert out.getvalue() == ""

    def test_error_writes_json_document_to_stderr_with_message_and_status(self) -> None:
        message = "bad data type"
        out, err = io.StringIO(), io.StringIO()
        output = Output(json_mode=True, stdout=out, stderr=err)

        output.emit_error(message, status_code=HTTPStatus.BAD_REQUEST)

        assert json.loads(err.getvalue()) == {
            "message": message,
            "status_code": int(HTTPStatus.BAD_REQUEST),
        }
        assert out.getvalue() == ""

    def test_error_omits_status_code_when_absent(self) -> None:
        message = "usage problem"
        out, err = io.StringIO(), io.StringIO()
        output = Output(json_mode=True, stdout=out, stderr=err)

        output.emit_error(message)

        assert json.loads(err.getvalue()) == {"message": message}

    def test_error_includes_details_under_errors_key(self) -> None:
        message = "Annotation has 1 validation error(s)"
        errors = [{"row": 1, "message": "Invalid scientist"}]
        out, err = io.StringIO(), io.StringIO()
        output = Output(json_mode=True, stdout=out, stderr=err)

        output.emit_error(message, status_code=HTTPStatus.BAD_REQUEST, details=errors)

        assert json.loads(err.getvalue()) == {
            "message": message,
            "status_code": int(HTTPStatus.BAD_REQUEST),
            "errors": errors,
        }
        assert out.getvalue() == ""


class TestFormatIssue:

    def test_formats_row_and_message(self) -> None:
        assert format_issue({"row": 1, "message": "bad"}) == "row 1: bad"

    def test_message_without_row_has_no_prefix(self) -> None:
        assert format_issue({"message": "bad"}) == "bad"

    def test_falls_back_to_str_for_other_shapes(self) -> None:
        issue = {"code": "E123"}

        assert format_issue(issue) == str(issue)
