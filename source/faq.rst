FAQ
===

"This field is required" error when uploading a sample
------------------------------------------------------

If you see an error like::

    flowbio.v2.exceptions.BadRequestError: {'strandedness': ['This field is required.']}

this means your upload is missing a metadata attribute that the server
requires for the chosen sample type. The field name in the error
(``strandedness`` in this example) tells you which attribute is missing.

See :ref:`metadata-attributes` for how to discover which attributes are
required and how to pass them when uploading.

"Select a valid choice" error when uploading a sample
-----------------------------------------------------

If you see an error like::

    flowbio.v2.exceptions.BadRequestError: {'strandedness': ['Select a valid choice. That choice is not one of the available choices.']}

this means the value you provided for a metadata attribute is not one of
the accepted options. Some attributes only accept values from a fixed set.

See :ref:`metadata-attributes` for how to discover the valid ``options``
for each attribute.
