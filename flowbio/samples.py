"""Samples queries and mutations"""

from .queries import SAMPLE

class SamplesClient:

    def sample(self, id):
        """Returns a sample.
        
        :param str id: The ID of the sample.
        :rtype: ``dict``"""

        return self.execute(SAMPLE, variables={"id": id})["data"]["sample"]