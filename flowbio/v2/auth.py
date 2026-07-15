"""
To authenticate, pass credentials to :meth:`Client.log_in <flowbio.v2.Client.log_in>`.

**Username and password** — the most common method::

    from flowbio.v2 import Client, UsernamePasswordCredentials

    client = Client()
    client.log_in(UsernamePasswordCredentials(
        username="alice", password="s3cret",
    ))

**Existing token** — useful when you already have a token::

    from flowbio.v2 import Client
    from flowbio.v2.auth import TokenCredentials

    client = Client()
    client.log_in(TokenCredentials(token="your.jwt.token"))
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flowbio.v2._transport import HttpTransport


class Credentials(ABC):
    """Abstract base class for authentication credentials.

    Subclasses implement :meth:`authenticate` to perform their specific
    authentication flow against the Flow API.
    """

    @abstractmethod
    def authenticate(self, transport: HttpTransport) -> None:
        """Authenticate against the Flow API using this credential.

        :param transport: The HTTP transport to authenticate with.
        """
        ...


class TokenCredentials(Credentials):
    """Authenticates using an existing JWT token.

    Sets the token directly on the transport without making any HTTP
    requests. Useful when a token has already been obtained through
    another mechanism (e.g. the v1 client).

    :param token: The JWT access token.

    Example::

        from flowbio.v2 import Client
        from flowbio.v2.auth import TokenCredentials

        client = Client()
        client.log_in(TokenCredentials(token="your.jwt.token"))
    """

    def __init__(self, token: str) -> None:
        self._token = token

    def authenticate(self, transport: HttpTransport) -> None:
        """Set the token on the transport without making HTTP requests.

        :param transport: The HTTP transport to authenticate with.
        """
        transport.set_token(self._token)


class UsernamePasswordCredentials(Credentials):
    """Authenticates to the Flow API with a username and password.

    :param username: The user's username.
    :param password: The user's password.
    """

    def __init__(self, username: str, password: str) -> None:
        self.username = username
        self.password = password

    def authenticate(self, transport: HttpTransport) -> None:
        """Authenticate by posting credentials to the login endpoint.

        :param transport: The HTTP transport to authenticate with.
        :raises BadRequestError: If the credentials are invalid.
        """
        response = transport.post("/login", json={
            "username": self.username,
            "password": self.password,
        })
        transport.set_token(response["token"])
