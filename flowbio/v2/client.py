from flowbio.v2._transport import HttpTransport
from flowbio.v2.auth import Credentials


class Client:
    """Client for the Flow REST API.

    Provides authentication and access to the Flow platform.

    Usage::

        from flowbio.v2 import Client
        from flowbio.v2.auth import UsernamePasswordCredentials

        client = Client()
        client.log_in(UsernamePasswordCredentials(
            username="alice", password="s3cret",
        ))

    :param base_url: The base URL of the Flow API. Defaults to
        ``"https://app.flow.bio/api"``.
    """

    def __init__(self, base_url: str = "https://app.flow.bio/api") -> None:
        self._transport = HttpTransport(base_url)

    def log_in(self, credentials: Credentials) -> None:
        """Authenticate with the Flow API.

        Delegates to the provided credentials strategy, which performs
        the authentication flow and stores the access token for
        subsequent requests.

        :param credentials: The credentials to authenticate with.
        :raises BadRequestError: If the credentials are invalid.
        """
        credentials.authenticate(self._transport)
