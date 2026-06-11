flowbio
=======

The flowbio Python library is a wrapper around the Flow API, allowing you to
write Python scripts that interact with an instance of Flow.

Installation
------------

Install with pip::

    pip install flowbio

Requires Python 3.11+. Dependencies (``requests``, ``pydantic``, ``tqdm``, etc.)
are installed automatically.

Overview
--------

Everything starts with creating a :class:`~flowbio.v2.Client`. This is your
connection to Flow — once you log in, you use it to upload samples, browse
metadata, manage projects, and anything else the library supports::

    from flowbio.v2 import Client
    from flowbio.v2.auth import UsernamePasswordCredentials

    client = Client()
    client.log_in(UsernamePasswordCredentials("you@example.com", "password"))

    # Now use client.samples.upload_sample(...), client.samples.upload_multiplexed_data(...), etc.

The :class:`~flowbio.v2.Client` is the recommended starting point and is
under active development. The :class:`legacy client <flowbio.Client>` is
being phased out but remains available for functionality not yet covered
by v2.

Command-line interface
----------------------

The same upload operations are available from the terminal via the ``flowbio``
command, for both interactive use and automated agents (``--json`` output with
stable exit codes). Log in once and your token is reused on later calls::

    # Upload a single demultiplexed sample
    flowbio samples upload --name liver_r1 --sample-type RNA-Seq \
        --reads1 ./liver_R1.fastq.gz --reads2 ./liver_R2.fastq.gz \
        --metadata strandedness=reverse

    # Upload a generic data file, with machine-readable output
    flowbio data upload ./counts.tsv --json

    # Upload many samples from a CSV sample sheet
    flowbio samples batch-template --sample-type RNA-Seq -o samples.csv
    flowbio samples upload-batch --sheet samples.csv --sample-type RNA-Seq

See :doc:`cli` for authentication, output modes, the exit-code contract, and a
worked example per command.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   Home <self>
   v2/index
   cli
   legacy
   faq
