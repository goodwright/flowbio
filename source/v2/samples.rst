Samples
=======

.. automodule:: flowbio.v2.samples
   :no-members:

Uploading Samples
-----------------

Use :meth:`~flowbio.v2.samples.SampleResource.upload_sample` to upload
demultiplexed (individual) samples. Each call creates one sample with one
or more data files::

    from pathlib import Path

    sample = client.samples.upload_sample(
        name="My RNA-Seq Sample",
        sample_type="RNA-Seq",
        data={"reads1": Path("reads_R1.fastq.gz")},
        metadata={"strandedness": "forward"},
    )

For paired-end samples, provide both ``reads1`` and ``reads2``::

    sample = client.samples.upload_sample(
        name="Paired-end Sample",
        sample_type="RNA-Seq",
        data={
            "reads1": Path("R1.fastq.gz"),
            "reads2": Path("R2.fastq.gz"),
        },
    )

See :meth:`~flowbio.v2.samples.SampleResource.upload_sample` for the full
list of parameters including metadata, project, and organism options.

.. _metadata-attributes:

Metadata attributes
~~~~~~~~~~~~~~~~~~~

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

.. _multiplexed-uploads:

Multiplexed uploads
~~~~~~~~~~~~~~~~~~~

Multiplexed uploads let you upload reads that contain data from multiple
samples in a single file, along with an annotation sheet that describes how
the reads should be demultiplexed.

The workflow has three steps:

1. **Download an annotation template** for your sample type
2. **Fill in the template** with one row per sample (names, metadata, etc.)
3. **Upload the reads and annotation** together

Download a template
^^^^^^^^^^^^^^^^^^^

Use :meth:`~flowbio.v2.samples.SampleResource.get_annotation_template` to
get a pre-formatted spreadsheet for your sample type::

    from pathlib import Path

    template = client.samples.get_annotation_template("rna_seq")
    Path("annotation_template.xlsx").write_bytes(template)

Open the file in a spreadsheet editor, fill in one row per sample, and save
it.

Upload reads and annotation
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Pass the reads files and the completed annotation sheet to
:meth:`~flowbio.v2.samples.SampleResource.upload_multiplexed_data`::

    from pathlib import Path

    result = client.samples.upload_multiplexed_data(
        reads={"reads1": Path("multiplexed_R1.fastq.gz")},
        annotation=Path("annotation.xlsx"),
    )
    print(f"Data IDs: {result.data_ids}")
    print(f"Annotation ID: {result.annotation_id}")

For paired-end multiplexed reads, provide both ``reads1`` and ``reads2``::

    result = client.samples.upload_multiplexed_data(
        reads={
            "reads1": Path("multiplexed_R1.fastq.gz"),
            "reads2": Path("multiplexed_R2.fastq.gz"),
        },
        annotation=Path("annotation.xlsx"),
    )

Handling annotation warnings
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The server validates the annotation sheet before uploading reads. If
there are hard validation errors, an
:class:`~flowbio.v2.exceptions.AnnotationValidationError` is raised
and no reads are uploaded.

Some issues produce **warnings** rather than errors (e.g. unusual but
valid values). By default, warnings are automatically accepted and
included in the result for inspection::

    result = client.samples.upload_multiplexed_data(
        reads={"reads1": Path("multiplexed_R1.fastq.gz")},
        annotation=Path("annotation.xlsx"),
    )
    if result.warnings:
        for warning in result.warnings:
            print(f"Warning: {warning}")

To reject the upload when warnings are present, set
``ignore_warnings=False``::

    result = client.samples.upload_multiplexed_data(
        reads={"reads1": Path("multiplexed_R1.fastq.gz")},
        annotation=Path("annotation.xlsx"),
        ignore_warnings=False,
    )

This raises :class:`~flowbio.v2.exceptions.AnnotationValidationError`
if the annotation has any warnings.

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

.. autoclass:: flowbio.v2.samples.MultiplexedUpload
   :no-members: