from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING

from pydantic import BaseModel

from flowbio.v2._pagination import PageIterator

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


class Project(BaseModel, frozen=True):
    """A project that samples can be assigned to.

    Example::

        projects = client.samples.get_owned_projects()
        for p in projects:
            print(f"{p.id}: {p.name}")
    """

    id: str
    name: str
    description: str


class Organism(BaseModel, frozen=True):
    """An organism that a sample can be associated with.

    Example::

        organisms = client.samples.get_organisms()
        for o in organisms:
            print(f"{o.id}: {o.name} ({o.latin_name})")
    """

    id: str
    name: str
    latin_name: str


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
        return [SampleType(**item) for item in self._transport.get("/samples/types")]

    def get_owned_projects(self) -> Sequence[Project]:
        """Return the projects owned by the authenticated user.

        Requires authentication. Results are paginated lazily — pages
        are only fetched from the API as you iterate through the
        results.

        The total count is available via ``len()`` without fetching
        all pages::

            projects = client.samples.get_owned_projects()
            print(f"You have {len(projects)} projects")

        Iterate to access individual projects::

            for project in client.samples.get_owned_projects():
                print(f"{project.id}: {project.name}")

        Or convert to a list to fetch everything at once::

            all_projects = list(client.samples.get_owned_projects())
        """
        return PageIterator(
            self._transport,
            "/projects/owned",
            items_key="projects",
            item_factory=lambda item: Project(**item),
        )

    def get_organisms(self) -> list[Organism]:
        """Return the available organisms.

        Example::

            organisms = client.samples.get_organisms()
            for o in organisms:
                print(f"{o.id}: {o.name} ({o.latin_name})")
        """
        return [Organism(**item) for item in self._transport.get("/organisms")]

    def get_metadata_attributes(self) -> list[MetadataAttribute]:
        """Return the available metadata attributes for samples.

        Fetches all attributes and, for those with restricted options,
        fetches the valid values. Attributes where any user-provided
        value is accepted will have ``options`` set to ``None``.

        Example::

            attributes = client.samples.get_metadata_attributes()
            required = [a for a in attributes if a.required]
        """
        return [self._create_metadata_attribute(item) for item in (self._transport.get("/samples/metadata"))]

    def _create_metadata_attribute(self, item: dict) -> MetadataAttribute:
        item["required_for_sample_types"] = [
            link["sample_type_identifier"]
            for link in item.get("sample_type_links", [])
            if link.get("required")
        ]
        item["options"] = self._resolve_options(item)
        return MetadataAttribute(**item)

    def _resolve_options(self, item: dict) -> list[str] | None:
        if item.get("allow_user_terms"):
            return None
        if not item.get("has_options"):
            return None
        options_response = self._transport.get(
            f"/samples/metadata/{item['identifier']}/options",
        )
        return [opt["value"] for opt in options_response["options"]]
