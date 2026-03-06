from dataclasses import dataclass

from flowbio.v2._transport import HttpTransport
from flowbio.v2.auth import Credentials
from flowbio.v2.samples import SampleResource


@dataclass(frozen=True)
class ClientConfig:
    """Configuration for the Flow API client.

    :param chunk_size: Size of each upload chunk in bytes.
        Defaults to 1 MB.
    :param show_progress: Whether to display progress bars during
        file uploads. Defaults to ``True``.

    Example usage::

        from flowbio.v2 import Client, ClientConfig

        client = Client(config=ClientConfig(
            chunk_size=5_000_000,
            show_progress=False,
        ))
    """

    chunk_size: int = 1_000_000
    show_progress: bool = True


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

    If you are connecting to a private instance of Flow, you can pass that in the url parameter of the constructor::

        client = Client(base_url="https://mycompany.flow.bio/api")

    :param base_url: The base URL of the Flow API. Defaults to
        ``"https://app.flow.bio/api"``.
    :param config: Optional client configuration. If not provided,
        defaults are used.
    """

    def __init__(
        self,
        base_url: str = "https://app.flow.bio/api",
        config: ClientConfig | None = None,
    ) -> None:
        self._transport = HttpTransport(base_url)
        self._config = config or ClientConfig()
        self._samples = SampleResource(self._transport, self._config)

    @property
    def samples(self) -> SampleResource:
        """Access sample-related operations (types, metadata, upload)."""
        return self._samples

    def log_in(self, credentials: Credentials) -> None:
        """Authenticate with the Flow API.

        Delegates to the provided credentials strategy, which performs
        the authentication flow and stores the access token for
        subsequent requests.

        :param credentials: The credentials to authenticate with. See :mod:`flowbio.v2.auth` for details.
        :raises BadRequestError: If the credentials are invalid.
        """
        credentials.authenticate(self._transport)
