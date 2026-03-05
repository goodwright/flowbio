import httpx
import pytest
import respx

from flowbio.v2.client import Client
from flowbio.v2.samples import MetadataAttribute, Project, SampleResource, SampleType

from tests.unit.v2.conftest import DEFAULT_BASE_URL


class TestSampleResourceWiring:

    def test_client_has_samples_attribute(self) -> None:
        client = Client()

        assert isinstance(client.samples, SampleResource)

    def test_samples_is_read_only(self) -> None:
        client = Client()

        with pytest.raises(AttributeError):
            client.samples = "something else"


class TestGetTypes:

    @respx.mock
    def test_parses_api_response_into_sample_type_models(self) -> None:
        identifier = "rna_seq"
        name = "RNA-Seq"
        description = "RNA sequencing data"
        respx.get(f"{DEFAULT_BASE_URL}/samples/types").mock(
            return_value=httpx.Response(200, json=[
                {
                    "identifier": identifier,
                    "name": name,
                    "description": description,
                    "extra_field": "ignored",
                },
            ]),
        )

        client = Client()
        result = client.samples.get_types()

        assert len(result) == 1
        assert result[0] == SampleType(
            identifier=identifier, name=name, description=description,
        )

    @respx.mock
    def test_returns_empty_list_when_no_types(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/samples/types").mock(
            return_value=httpx.Response(200, json=[]),
        )

        client = Client()
        result = client.samples.get_types()

        assert result == []


class TestGetMetadataAttributes:

    @respx.mock
    def test_parses_attributes_without_options(self) -> None:
        identifier = "genome_build"
        name = "Genome Build"
        description = "Reference genome"
        respx.get(f"{DEFAULT_BASE_URL}/samples/metadata").mock(
            return_value=httpx.Response(200, json=[
                {
                    "identifier": identifier,
                    "name": name,
                    "description": description,
                    "required": True,
                    "required_for_public": False,
                    "all_sample_types": True,
                    "allow_user_terms": False,
                    "regex_validator": r"^hg\d+$",
                    "has_options": False,
                    "sample_type_links": [],
                },
            ]),
        )

        client = Client()
        result = client.samples.get_metadata_attributes()

        assert len(result) == 1
        assert result[0] == MetadataAttribute(
            identifier=identifier,
            name=name,
            description=description,
            required=True,
            required_for_sample_types=[],
            options=None,
        )

    @respx.mock
    def test_fetches_options_when_restricted(self) -> None:
        identifier = "cell_type"
        respx.get(f"{DEFAULT_BASE_URL}/samples/metadata").mock(
            return_value=httpx.Response(200, json=[
                {
                    "identifier": identifier,
                    "name": "Cell Type",
                    "description": "The cell type",
                    "required": False,
                    "required_for_public": False,
                    "all_sample_types": True,
                    "allow_user_terms": False,
                    "has_options": True,
                    "regex_validator": None,
                    "sample_type_links": [],
                },
            ]),
        )
        respx.get(f"{DEFAULT_BASE_URL}/samples/metadata/{identifier}/options").mock(
            return_value=httpx.Response(200, json={
                "options": [
                    {"value": "Neuron"},
                    {"value": "Fibroblast"},
                ],
            }),
        )

        client = Client()
        result = client.samples.get_metadata_attributes()

        assert result[0].options == ["Neuron", "Fibroblast"]

    @respx.mock
    def test_options_is_none_when_user_terms_allowed(self) -> None:
        identifier = "cell_type"
        respx.get(f"{DEFAULT_BASE_URL}/samples/metadata").mock(
            return_value=httpx.Response(200, json=[
                {
                    "identifier": identifier,
                    "name": "Cell Type",
                    "description": "The cell type",
                    "required": False,
                    "required_for_public": False,
                    "all_sample_types": True,
                    "allow_user_terms": True,
                    "has_options": True,
                    "regex_validator": None,
                    "sample_type_links": [],
                },
            ]),
        )

        client = Client()
        result = client.samples.get_metadata_attributes()

        assert result[0].options is None

    @respx.mock
    def test_populates_required_for_sample_types_from_links(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/samples/metadata").mock(
            return_value=httpx.Response(200, json=[
                {
                    "identifier": "strandedness",
                    "name": "Strandedness",
                    "description": "Strand info",
                    "required": False,
                    "required_for_public": False,
                    "all_sample_types": False,
                    "allow_user_terms": False,
                    "regex_validator": None,
                    "has_options": False,
                    "sample_type_links": [
                        {"sample_type_identifier": "rna_seq", "required": True},
                        {"sample_type_identifier": "chip_seq", "required": False},
                        {"sample_type_identifier": "atac_seq", "required": True},
                    ],
                },
            ]),
        )

        client = Client()
        result = client.samples.get_metadata_attributes()

        assert result[0].required_for_sample_types == ["rna_seq", "atac_seq"]


class TestGetOwnedProjects:

    @respx.mock
    def test_parses_response_into_project_models(self) -> None:
        project_id = "123"
        project_name = "My Project"
        description = "A test project"
        respx.get(f"{DEFAULT_BASE_URL}/projects/owned").mock(
            return_value=httpx.Response(200, json={
                "count": 1,
                "projects": [
                    {
                        "id": project_id,
                        "name": project_name,
                        "description": description,
                        "extra": "ignored",
                    },
                ],
            }),
        )

        client = Client()
        result = client.samples.get_owned_projects()

        assert len(result) == 1
        assert result[0] == Project(
            id=project_id, name=project_name, description=description,
        )

    @respx.mock
    def test_returns_empty_sequence_when_no_projects(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/projects/owned").mock(
            return_value=httpx.Response(200, json={
                "count": 0,
                "projects": [],
            }),
        )

        client = Client()
        result = client.samples.get_owned_projects()

        assert len(result) == 0
        assert list(result) == []

    @respx.mock
    def test_paginates_across_multiple_pages(self) -> None:
        route = respx.get(f"{DEFAULT_BASE_URL}/projects/owned")
        route.side_effect = [
            httpx.Response(200, json={
                "count": 3,
                "projects": [
                    {"id": "1", "name": "P1", "description": ""},
                    {"id": "2", "name": "P2", "description": ""},
                ],
            }),
            httpx.Response(200, json={
                "count": 3,
                "projects": [
                    {"id": "3", "name": "P3", "description": ""},
                ],
            }),
        ]

        client = Client()
        result = list(client.samples.get_owned_projects())

        assert len(result) == 3
        assert [p.name for p in result] == ["P1", "P2", "P3"]
