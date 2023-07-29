from .base import ServerTestCase

class LoginTests(ServerTestCase):
    
    def test_can_login(self):
        # No header
        self.assertNotIn("Authorization", self.client.headers)
        self.assertNotIn("localhost.local", self.client.session.cookies._cookies)

        # Can't access protected resource
        resp = self.client.execute("{ me { username } }")
        self.assertIsNone(resp["data"]["me"])

        # Login
        self.client.login("testuser", "testpassword")

        # Header is set
        self.assertIn("Authorization", self.client.headers)

        # Cookie is set
        cookie = self.client.session.cookies._cookies["localhost.local"]["/"]["flow_refresh_token"]
        self.assertIn("HttpOnly", cookie._rest)
        token = cookie.value
        self.assertEqual(token.split(".")[0], self.client.headers["Authorization"].split(".")[0])

        # Can access protected resource
        resp = self.client.execute("{ me { username } }")
        self.assertEqual(resp["data"]["me"]["username"], "testuser")