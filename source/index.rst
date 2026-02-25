.. flowbio documentation master file, created by
   sphinx-quickstart on Mon Feb 23 18:13:09 2026.
   You can adapt this file completely to your liking, but it should at least
   contain the root `toctree` directive.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

flowbio documentation
=====================

The flowbio Python library is a wrapper around the Flow API, allowing you to easily write Python scripts that interact with an instance of Flow.

Installation
------------

You can install flowbio using pip::

    pip install flowbio

Example Usage
-------------

Example usage::

    import flowbio

    client = flowbio.Client()
    client.login("your_username", "your_password")

    # Upload standard data
    data = client.upload_data("/path/to/file.fa", progress=True, retries=5)
    print(data)

    # Upload sample
    sample = client.upload_sample(
        "My Sample Name",
        "/path/to/reads1.fastq.gz",
        "/path/to/reads2.fastq.gz", # optional
        progress=True,
        retries=5,
        metadata={
            "sample_type": "RNA-Seq",
            "scientist": "Charles Darwin",
            "strandedness": "reverse",
        }
    )
    print(sample)

    # Upload multiplexed
    multiplexed = client.upload_multiplexed(
        "/path/to/reads.fastq.gz",
        progress=True,
        retries=5,
    )
    print(multiplexed)

    # Upload annotation
    annotation = client.upload_annotation(
        "/path/to/annotation.csv",
        progress=True,
        retries=5,
    )
    print(annotation)

    # Run pipeline
    execution = client.run_pipeline(
        "RNA-Seq",
        "3.8.1",
        "23.04.3",
        params={"param1": "param2"},
        data_params={"fasta": 123456789},
    )

API Reference
-------------

.. autoclass:: flowbio.Client
   :members: login, upload_sample
