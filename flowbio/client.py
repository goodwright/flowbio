import kirjava
from .upload import UploadClient
from .samples import SamplesClient

class GraphQlError(Exception):
    pass



class Client(kirjava.Client, UploadClient, SamplesClient):

    def execute(self, *args, **kwargs):
        """Executes a GraphQL query and raises an exception if it fails."""

        resp = super().execute(*args, **kwargs)
        if "errors" in resp:
            raise GraphQlError(resp["errors"])
        return resp
    

    def login(self, username, password):
        """Acquires the relevant access token for the client."""
        
        response = self.execute("""mutation login(
            $username: String! $password: String!
        ) { login(username: $username password: $password) {
            accessToken
        } }""", variables={"username": username, "password": password})
        token = response["data"]["login"]["accessToken"]
        self.headers["Authorization"] = token
    

    def user(self, username):
        """Returns a user object."""

        response = self.execute("""query user(
            $username: String!
        ) { user(username: $username) {
            id username name
        } }""", variables={"username": username})
        return response["data"]["user"]