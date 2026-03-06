from pathlib import Path
from unittest.mock import ANY

import httpx
import pytest
import respx

from flowbio.v2.client import Client, ClientConfig
from flowbio.v2.samples import (
    MetadataAttribute,
    Organism,
    Project,
    SampleResource,
    SampleType,
    Sample,
)

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


class TestGetOrganisms:

    @respx.mock
    def test_parses_api_response_into_organism_models(self) -> None:
        organism_id = "Hs"
        name = "Human"
        latin_name = "Homo sapiens"
        respx.get(f"{DEFAULT_BASE_URL}/organisms").mock(
            return_value=httpx.Response(200, json=[
                {
                    "id": organism_id,
                    "name": name,
                    "latin_name": latin_name,
                    "latest_fileset": {},
                },
            ]),
        )

        client = Client()
        result = client.samples.get_organisms()

        assert len(result) == 1
        assert result[0] == Organism(
            id=organism_id, name=name, latin_name=latin_name,
        )

    @respx.mock
    def test_returns_empty_list_when_no_organisms(self) -> None:
        respx.get(f"{DEFAULT_BASE_URL}/organisms").mock(
            return_value=httpx.Response(200, json=[]),
        )

        client = Client()
        result = client.samples.get_organisms()

        assert result == []


class TestUploadSample:

    @respx.mock
    def test_single_file_upload(self, tmp_path: Path) -> None:
        file_content = b"ATCGATCG"
        file_path = tmp_path / "reads.fastq"
        file_path.write_bytes(file_content)
        sample_id = "sample_123"
        route = respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            return_value=httpx.Response(200, json={
                "sample_id": sample_id,
                "data_id": "data_456",
            }),
        )

        client = Client()
        result = client.samples.upload_sample(
            name="My Sample",
            sample_type="rna_seq",
            data={"reads1": file_path},
        )

        assert result == Sample(id=sample_id)
        assert route.call_count == 1
        request = route.calls[0].request
        assert b"is_last_sample" in request.content
        assert b"My Sample" in request.content
        assert b"rna_seq" in request.content

    @respx.mock
    def test_passes_metadata_as_form_fields(self, tmp_path: Path) -> None:
        file_path = tmp_path / "reads.fastq"
        file_path.write_bytes(b"ATCG")
        respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            return_value=httpx.Response(200, json={
                "sample_id": "s1", "data_id": "d1",
            }),
        )

        client = Client()
        client.samples.upload_sample(
            name="My Sample",
            sample_type="rna_seq",
            data={"reads1": file_path},
            metadata={"strandedness": "forward"},
        )

        request = respx.calls[0].request
        assert b"strandedness" in request.content

    @respx.mock
    def test_passes_project_and_organism(self, tmp_path: Path) -> None:
        file_path = tmp_path / "reads.fastq"
        file_path.write_bytes(b"ATCG")
        respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            return_value=httpx.Response(200, json={
                "sample_id": "s1", "data_id": "d1",
            }),
        )

        client = Client()
        client.samples.upload_sample(
            name="My Sample",
            sample_type="rna_seq",
            data={"reads1": file_path},
            project_id="proj_1",
            organism_id="Hs",
        )

        request = respx.calls[0].request
        assert b"proj_1" in request.content
        assert b"Hs" in request.content

    @respx.mock
    def test_two_file_upload(self, tmp_path: Path) -> None:
        file1 = tmp_path / "R1.fastq"
        file2 = tmp_path / "R2.fastq"
        file1.write_bytes(b"ATCG")
        file2.write_bytes(b"GCTA")
        first_data_id = "data_1"
        route = respx.post(f"{DEFAULT_BASE_URL}/upload/sample")
        route.side_effect = [
            httpx.Response(200, json={
                "sample_id": None, "data_id": first_data_id,
            }),
            httpx.Response(200, json={
                "sample_id": "sample_1", "data_id": "data_2",
            }),
        ]

        client = Client()
        result = client.samples.upload_sample(
            name="Paired Sample",
            sample_type="rna_seq",
            data={"reads1": file1, "reads2": file2},
        )

        assert result == Sample(id="sample_1")
        assert route.call_count == 2
        second_request = route.calls[1].request
        assert b"previous_data" in second_request.content
        assert first_data_id.encode() in second_request.content

    @respx.mock
    def test_uploads_in_chunks(self, tmp_path: Path) -> None:
        file_path = tmp_path / "reads.fastq"
        file_path.write_bytes(b"A" * 100)
        route = respx.post(f"{DEFAULT_BASE_URL}/upload/sample")
        route.side_effect = [
            httpx.Response(200, json={"sample_id": None, "data_id": "d1"}),
            httpx.Response(200, json={"sample_id": None, "data_id": "d1"}),
            httpx.Response(200, json={"sample_id": "s1", "data_id": "d1"}),
        ]

        client = Client(config=ClientConfig(chunk_size=40, show_progress=False))
        client.samples.upload_sample(
            name="My Sample",
            sample_type="rna_seq",
            data={"reads1": file_path},
        )

        assert route.call_count == 3

    def test_rejects_invalid_reads_key(self, tmp_path: Path) -> None:
        file_path = tmp_path / "reads.fastq"
        file_path.write_bytes(b"ATCG")

        client = Client()

        with pytest.raises(ValueError, match="reads3"):
            client.samples.upload_sample(
                name="Bad Sample",
                sample_type="rna_seq",
                data={"reads1": file_path, "reads3": file_path},
            )

    def test_rejects_reads2_without_reads1(self, tmp_path: Path) -> None:
        file_path = tmp_path / "reads.fastq"
        file_path.write_bytes(b"ATCG")

        client = Client()

        with pytest.raises(ValueError, match="reads1"):
            client.samples.upload_sample(
                name="Bad Sample",
                sample_type="rna_seq",
                data={"reads2": file_path},
            )

    @respx.mock
    def test_reads_keys_are_uploaded_in_order(self, tmp_path: Path) -> None:
        file1 = tmp_path / "R1.fastq"
        file2 = tmp_path / "R2.fastq"
        file1.write_bytes(b"READ1")
        file2.write_bytes(b"READ2")
        route = respx.post(f"{DEFAULT_BASE_URL}/upload/sample")
        route.side_effect = [
            httpx.Response(200, json={"sample_id": None, "data_id": "d1"}),
            httpx.Response(200, json={"sample_id": "s1", "data_id": "d2"}),
        ]

        client = Client()
        client.samples.upload_sample(
            name="Paired",
            sample_type="rna_seq",
            data={"reads2": file2, "reads1": file1},
        )

        assert b"READ1" in route.calls[0].request.content
        assert b"READ2" in route.calls[1].request.content

    @respx.mock
    def test_non_reads_keys_are_accepted(self, tmp_path: Path) -> None:
        file_path = tmp_path / "counts.csv"
        file_path.write_bytes(b"gene,count")
        respx.post(f"{DEFAULT_BASE_URL}/upload/sample").mock(
            return_value=httpx.Response(200, json={
                "sample_id": "s1", "data_id": "d1",
            }),
        )

        client = Client()
        result = client.samples.upload_sample(
            name="Word Count",
            sample_type="word_count",
            data={"input": file_path},
        )

        assert result == Sample(id="s1")
