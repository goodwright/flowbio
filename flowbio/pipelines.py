"""Pipelines queries and mutations"""

import json
from .queries import PIPELINE, EXECUTION
from .mutations import RUN_PIPELINE

class PipelinesClient:
    
    def run_pipeline(self, name, version, nextflow_version, params=None, data_params=None, sample_params=None, genome=None):
        """Runs a pipeline.
        
        :param str name: The name of the pipeline.
        :param str version: The version of the pipeline.
        :param str nextflow_version: The version of Nextflow to use.
        :param dict params: The parameters to pass to the pipeline.
        :param dict data_params: The data parameters to pass to the pipeline.
        :param dict sample_params: The sample parameters to pass to the pipeline.
        :param str genome: The genome to use.
        :rtype: ``dict``"""

        categories = self.execute(PIPELINE)["data"]["pipelineCategories"]
        pipelines = [p for c in categories for s in c["subcategories"] for p in s["pipelines"]]
        lookup = {p["name"]: {p["version"]["name"]: p["version"]["id"]} for p in pipelines}
        if name not in lookup: raise ValueError("Pipeline not found")
        if version not in lookup[name]: raise ValueError("Pipeline version not found")
        version_id = lookup[name][version]
        params = json.dumps(params or {})
        data_params = json.dumps(data_params or {})
        sample_params = json.dumps(sample_params or {})
        resp = self.execute(RUN_PIPELINE, variables={
            "id": version_id, "nextflowVersion": nextflow_version,
            "params": params, "dataParams": data_params,
            "sampleParams": sample_params, "genome": genome
        })
        execution_id = resp["data"]["runPipeline"]["execution"]["id"]
        return self.execution(execution_id)
    

    def execution(self, id):
        """Returns an execution.
        
        :param str id: The ID of the execution.
        :rtype: ``dict``"""

        return self.execute(EXECUTION, variables={"id": id})["data"]["execution"]