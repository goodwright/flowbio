import kirjava
import time
from .upload import UploadClient
from .samples import SamplesClient

class GraphQlError(Exception):
    pass



class Client(kirjava.Client, UploadClient, SamplesClient):

    def __init__(self, url="https://api.flow.bio/graphql"):        
        super().__init__(url)
        self.last_token_refresh = None


    def execute(self, *args, check_token=True, **kwargs):
        __doc__ = kirjava.Client.execute.__doc__

        if self.last_token_refresh and check_token:
            age = time.time() - self.last_token_refresh
            if age > 60 * 20: self.refresh_token()
        resp = super().execute(*args, **kwargs)
        if "errors" in resp:
            raise GraphQlError(resp["errors"])
        return resp
    

    def login(self, username, password):
        """Acquires the relevant access token for the client.
        
        :param str username: The username of the user.
        :param str password: The password of the user."""
        
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