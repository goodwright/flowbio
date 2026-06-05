"""
The v2 client is the actively maintained interface to the Flow API. If there is
any functionality you'd like added, please create an issue on the
`GitHub repo <https://github.com/goodwright/flowbio>`_.

Quick Start
-----------

Create a client, log in, and upload a sample::

    from pathlib import Path
    from flowbio.v2 import Client, UsernamePasswordCredentials

    client = Client()
    client.log_in(UsernamePasswordCredentials(
        username="alice", password="s3cret",
    ))

    # See what sample types are available
    for st in client.samples.get_types():
        print(f"{st.identifier}: {st.name}")

    # Upload a sample
    sample = client.samples.upload_sample(
        name="My RNA-Seq Sample",
        sample_type="RNA-Seq",
        data={"reads1": Path("reads_R1.fastq.gz")},
    )
    print(f"Created sample {sample.id}")

    # Upload a generic data file
    data = client.data.upload_data(Path("counts.tsv"))
    print(f"Uploaded data {data.id}")
"""
from flowbio.v2.auth import TokenCredentials, UsernamePasswordCredentials
from flowbio.v2.client import Client, ClientConfig
from flowbio.v2.data import Data
from flowbio.v2.exceptions import AnnotationValidationError
from flowbio.v2.samples import MetadataAttribute, MultiplexedUpload, Organism, Project, Sample, SampleType

__all__ = [
    "AnnotationValidationError",
    "Client",
    "ClientConfig",
    "Data",
    "MetadataAttribute",
    "MultiplexedUpload",
    "Organism",
    "Project",
    "Sample",
    "SampleType",
    "TokenCredentials",
    "UsernamePasswordCredentials",
]
