import kirjava

class Client(kirjava.Client):
    
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