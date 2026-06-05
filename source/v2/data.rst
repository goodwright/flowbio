Data Files
==========

.. automodule:: flowbio.v2.data
   :no-members:

Uploading Data Files
--------------------

Use :meth:`~flowbio.v2.data.DataResource.upload_data` to upload a generic
data file. The file is uploaded in chunks and the created data file is
returned::

    from pathlib import Path

    data = client.data.upload_data(Path("counts.tsv"))
    print(f"Data ID: {data.id}")

Store the file under a different name than the local path with the
``filename`` override (the name must contain no spaces)::

    data = client.data.upload_data(
        Path("counts.tsv"),
        filename="experiment_42_counts.tsv",
    )

Tag the file with a ``DataType`` identifier, or upload an archive for the
server to unpack::

    data = client.data.upload_data(Path("reads.bam"), data_type="bam")

    archive = client.data.upload_data(Path("results.zip"), is_directory=True)

See :meth:`~flowbio.v2.data.DataResource.upload_data` for the full list of
parameters.

API Reference
-------------

.. autoclass:: flowbio.v2.data.DataResource
   :members:

Models
------

.. autopydantic_model:: flowbio.v2.data.Data
