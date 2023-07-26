flowbio
=======

A client for the Flow API.

.. code-block:: python
    
    import flowbio

    client = flowbio.Client()
    client.login("your_username", "your_password")

    # Upload standard data
    data = client.upload_data("/path/to/file.fa", progress=True)
    print(data)

    # Upload sample
    sample = client.upload_sample(
        "My Sample Name",
        "/path/to/reads1.fastq.gz",
        "/path/to/reads2.fastq.gz", # optional
        progress=True,
        metadata={
            "category": "RNA-Seq",
            "strandedness": "unstranded",
        }
    )
    print(sample)

    # Upload lane
    lane = client.upload_lane(
        "My Lane Name",
        "/path/to/annotation.xlsx",
        "/path/to/multiplexed.fastq.gz",
        ignore_warnings=True,
        progress=True
    )
    print(lane)
