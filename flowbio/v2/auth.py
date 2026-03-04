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
