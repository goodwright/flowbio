"""Samples queries and mutations"""

from .queries import SAMPLE, LANE

class SamplesClient:

    def sample(self, id):
        """Returns a sample.
        
        :param str id: The ID of the sample.
        :rtype: ``dict``"""

        return self.execute(SAMPLE, variables={"id": id})["data"]["sample"]
    

    def lane(self, id):
        """Returns a lane.
        
        :param str id: The ID of the lane.
        :rtype: ``dict``"""

        return self.execute(LANE, variables={"id": id})["data"]["lane"]