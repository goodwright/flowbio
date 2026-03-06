flowbio
=======

The flowbio Python library is a wrapper around the Flow API, allowing you to
write Python scripts that interact with an instance of Flow.

Installation
------------

Install with pip::

    pip install flowbio

Requires Python 3.8+. Dependencies (``requests``, ``pydantic``, ``tqdm``, etc.)
are installed automatically.

Overview
--------

The :class:`~flowbio.v2.Client` is the recommended client and is under active
development. The :class:`legacy client <flowbio.Client>` is being phased out
but remains available for functionality not yet covered by v2.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   Home <self>
   v2/index
   legacy
