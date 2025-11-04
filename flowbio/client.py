import webbrowser
from http import HTTPStatus

import kirjava
import time

import requests
from requests import HTTPError

from .upload import UploadClient
from .samples import SamplesClient
from .pipelines import PipelinesClient

class GraphQlError(Exception):
    pass



class Client(kirjava.Client, UploadClient, SamplesClient, PipelinesClient):

    def __init__(self, url="https://api.flow.bio/graphql", http_url="https://app.flow.bio/api"):
        super().__init__(url)
        self._http_url = http_url
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


    def _get_token_from_oidc(self, client_id, domain_url):
        """Acquires the relevant access token for the client.

        :param str client_id: The client ID of the application.
        :param str domain_url: The domain URL of the application."""

        response = requests.post(f"{domain_url}/oauth/device/code", data={"client_id": client_id, "scope": "openid profile email"})
        response.raise_for_status()

        device_code = response.json()["device_code"]
        user_code = response.json()["user_code"]
        verification_uri_complete = response.json()["verification_uri_complete"]
        interval = response.json()["interval"]

        if webbrowser.open_new(verification_uri_complete):
            print(f"Please verify the code {user_code} in your browser")
        else:
            print(f"Please visit {verification_uri_complete} and verify the code {user_code}.")

        while True:
            time.sleep(interval)
            response = requests.post(f"{domain_url}/oauth/token", data={"client_id": client_id, "device_code": device_code, "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            try:
                response.raise_for_status()
            except HTTPError:
                if response.json()["error"] == "authorization_pending" or response.json()["error"] == "slow_down":
                    time.sleep(interval)
                else:
                    raise
            else:
                id_token = response.json()["id_token"]
                break

        flow_response = requests.post(f"{self._http_url}/oidc-login", json={"id_token": id_token})
        flow_response.raise_for_status()
        return flow_response.json()["token"]

        # self.last_token_refresh = time.time()
        # self.headers["Authorization"] = token


    def login(self, username, password):
        """Acquires the relevant access token for the client.
        
        :param str username: The username of the user.
        :param str password: The password of the user."""

        response = requests.post(f"{self._http_url}/login", json={"username": username, "password": password})
        try:
            response.raise_for_status()
            token = response.json()["token"]
        except HTTPError:
            if response.status_code != HTTPStatus.NOT_IMPLEMENTED:
                raise
            response_data = response.json()
            if "client_id" not in response_data or "domain_url" not in response_data:
                raise
            token = self._get_token_from_oidc(response_data["client_id"], response_data["domain_url"])

        self.last_token_refresh = time.time()

        # response = self.execute("""mutation login(
        #     $username: String! $password: String!
        # ) { login(username: $username password: $password) {
        #     accessToken
        # } }""", variables={"username": username, "password": password})
        # self.last_token_refresh = time.time()
        # token = response["data"]["login"]["accessToken"]
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