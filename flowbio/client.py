import kirjava
import time
from importlib.metadata import version, PackageNotFoundError
from .upload import UploadClient
from .samples import SamplesClient
from .pipelines import PipelinesClient

class GraphQlError(Exception):
    pass


try:
    CLIENT_VERSION = version("flowbio")
except PackageNotFoundError:
    CLIENT_VERSION = "unknown"


class Client(kirjava.Client, UploadClient, SamplesClient, PipelinesClient):
    """This is the main client used to interface with the Flow api. You can instantiate it like so::

        client = flowbio.Client()

    Alternatively, if you are working with a private instance of Flow, you can instantiate it with your own url pointing
    to the Flow API::

        client = flowbio.Client("https://mycompany.flow.bio/api/graphql")
    """

    def __init__(self, url="https://api.flow.bio/graphql"):        
        super().__init__(url)
        self.last_token_refresh = None
        self.session.headers["User-Agent"] = f"flowbio-python/{CLIENT_VERSION}"


    def execute(self, *args, check_token=True, **kwargs):
        __doc__ = kirjava.Client.execute.__doc__

        if self.last_token_refresh and check_token:
            age = time.time() - self.last_token_refresh
            if age > 60 * 20: self.refresh_token()
        resp = super().execute(*args, **kwargs)
        if "errors" in resp:
            raise GraphQlError(resp["errors"])
        return resp
    

    def login(self, username: str, password: str) -> None:
        """Logs in the client and allows it to be used to access resources that requires a logged in user.
        
        :param username: The username of the user.
        :param password: The password of the user."""
        
        response = self.execute("""mutation login(
            $username: String! $password: String!
        ) { login(username: $username password: $password) {
            accessToken
        } }""", variables={"username": username, "password": password})
        self.last_token_refresh = time.time()
        token = response["data"]["login"]["accessToken"]
        self.headers["Authorization"] = token
    

    def refresh_token(self):
        """Refreshes the access token."""
        
        response = self.execute("{ accessToken }", check_token=False)
        self.last_token_refresh = time.time()
        token = response["data"]["accessToken"]
        self.headers["Authorization"] = token
    

    def user(self, username):
        """Returns a user object.
        
        :param str username: The username of the user.
        :rtype: ``dict``"""

        response = self.execute("""query user(
            $username: String!
        ) { user(username: $username) {
            id username name
        } }""", variables={"username": username})
        return response["data"]["user"]