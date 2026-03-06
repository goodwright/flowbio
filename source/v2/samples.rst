Samples
=======

.. automodule:: flowbio.v2.samples
   :no-members:

.. _metadata-attributes:

Metadata Attributes
-------------------

Samples can have metadata attributes attached to them. Some attributes are
required for all samples, while others are only required for specific sample
types. Use :meth:`~flowbio.v2.samples.SampleResource.get_metadata_attributes`
to discover what's available.

Each :class:`~flowbio.v2.samples.MetadataAttribute` tells you:

- Whether it's **universally required** (``required=True``)
- Whether it's **required for specific sample types**
  (``required_for_sample_types`` lists the sample type identifiers)
- Whether it has a **fixed set of valid values** (``options``) or accepts
  any free-text value (``options=None``)

Discover which attributes are required for a given sample type::

    attributes = client.samples.get_metadata_attributes()

    for attr in attributes:
        is_required = attr.required or "RNA-Seq" in attr.required_for_sample_types
        if is_required:
            if attr.options is not None:
                print(f"{attr.name} (required): choose from {attr.options}")
            else:
                print(f"{attr.name} (required): any value accepted")

Use the attribute identifiers as keys when uploading::

    from pathlib import Path

    attributes = client.samples.get_metadata_attributes()

    sample = client.samples.upload_sample(
        name="My Sample",
        sample_type="RNA-Seq",
        data={"reads1": Path("reads.fastq.gz")},
        metadata={
            attributes[0].identifier: "some value",
            attributes[1].identifier: attributes[1].options[0],
        },
    )

API Reference
-------------

.. autoclass:: flowbio.v2.samples.SampleResource
   :members:

Models
------

.. autoclass:: flowbio.v2.samples.Sample
   :no-members:

.. autoclass:: flowbio.v2.samples.SampleType
   :no-members:

.. autoclass:: flowbio.v2.samples.MetadataAttribute
   :no-members:

.. autoclass:: flowbio.v2.samples.Project
   :no-members:

.. autoclass:: flowbio.v2.samples.Organism
   :no-members:
