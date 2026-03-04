from flowbio.v2 import Client, UsernamePasswordCredentials


class TestTopLevelExports:

    def test_client_is_exported(self) -> None:
        from flowbio.v2.client import Client as DirectClient

        assert Client is DirectClient

    def test_username_password_credentials_is_exported(self) -> None:
        from flowbio.v2.auth import (
            UsernamePasswordCredentials as DirectCredentials,
        )

        assert UsernamePasswordCredentials is DirectCredentials


class TestSubmoduleExports:

    def test_credentials_importable_from_auth(self) -> None:
        from flowbio.v2.auth import Credentials

        assert Credentials is not None

    def test_flow_api_error_importable_from_exceptions(self) -> None:
        from flowbio.v2.exceptions import FlowApiError

        assert FlowApiError is not None

    def test_authentication_error_importable_from_exceptions(self) -> None:
        from flowbio.v2.exceptions import AuthenticationError

        assert AuthenticationError is not None

    def test_bad_request_error_importable_from_exceptions(self) -> None:
        from flowbio.v2.exceptions import BadRequestError

        assert BadRequestError is not None

    def test_not_found_error_importable_from_exceptions(self) -> None:
        from flowbio.v2.exceptions import NotFoundError

        assert NotFoundError is not None
