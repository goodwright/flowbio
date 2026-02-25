from unittest import TestCase

import flowbio
from flowbio.client import CLIENT_VERSION


class ClientTests(TestCase):
    def test_user_agent_is_set(self):
        url = "http://some.flow.instance.com"
        client = flowbio.Client(url)

        self.assertEqual(client.session.headers["User-Agent"], f"flowbio-python/{CLIENT_VERSION}")