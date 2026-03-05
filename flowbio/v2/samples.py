from __future__ import annotations

from typing import TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:
    from flowbio.v2._transport import HttpTransport


class SampleType(BaseModel, frozen=True):
    """A type of sample that can be uploaded to the Flow platform.

    Example::

        sample_types = client.samples.get_types()
        for st in sample_types:
            print(f"{st.identifier}: {st.name}")
    """

    identifier: str
    name: str
    description: str


class MetadataAttribute(BaseModel, frozen=True):
    """A metadata attribute that can be attached to a sample.

    :param identifier: Unique identifier for this attribute.
    :param name: Human-readable display name.
    :param description: Explanation of what this attribute represents.
    :param required: Whether this attribute is required at sample creation.
    :param required_for_sample_types: Sample type identifiers for which
        this attribute is required at creation.
    :param options: The list of valid values, or ``None`` if any value
        is accepted.

    Example::

        attributes = client.samples.get_metadata_attributes()
        for attr in attributes:
            if attr.options is not None:
                print(f"{attr.name}: choose from {attr.options}")
    """

    identifier: str
    name: str
    description: str
    required: bool
    required_for_sample_types: list[str]
    options: list[str] | None


class SampleResource:
    """Provides access to sample-related API endpoints.

    Accessed via :attr:`Client.samples`::

        client = Client()
        sample_types = client.samples.get_types()
    """

    def __init__(self, transport: HttpTransport) -> None:
        self._transport = transport

    def get_types(self) -> list[SampleType]:
        """Return the available sample types.

        Example::

            sample_types = client.samples.get_types()
            for st in sample_types:
                print(f"{st.identifier}: {st.name}")
        """
        response = self._transport.get("/samples/types")
        return [
            SampleType(
                identifier=item["identifier"],
                name=item["name"],
                description=item["description"],
            )
            for item in response
        ]

    def get_metadata_attributes(self) -> list[MetadataAttribute]:
        """Return the available metadata attributes for samples.

        Fetches all attributes and, for those with restricted options,
        fetches the valid values. Attributes where any user-provided
        value is accepted will have ``options`` set to ``None``.

        Example::

            attributes = client.samples.get_metadata_attributes()
            required = [a for a in attributes if a.required]
        """
        response = self._transport.get("/samples/metadata")
        attributes = []
        for item in response:
            required_for_sample_types = [
                link["sample_type_identifier"]
                for link in item.get("sample_type_links", [])
                if link.get("required")
            ]
            options = self._resolve_options(item)
            attributes.append(MetadataAttribute(
                identifier=item["identifier"],
                name=item["name"],
                description=item["description"],
                required=item["required"],
                required_for_sample_types=required_for_sample_types,
                options=options,
            ))
        return attributes

    def _resolve_options(self, item: dict) -> list[str] | None:
        if item.get("allow_user_terms"):
            return None
        if not item.get("has_options"):
            return None
        options_response = self._transport.get(
            f"/samples/metadata/{item['identifier']}/options",
        )
        return [opt["value"] for opt in options_response["options"]]
