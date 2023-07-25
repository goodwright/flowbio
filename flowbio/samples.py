from .queries import SAMPLE

class SamplesClient:

    def sample(self, id):
        """Returns a sample."""

        return self.execute(SAMPLE, variables={"id": id})["data"]["sample"]