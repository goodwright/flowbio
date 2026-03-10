"""
All sample operations are accessed via :attr:`Client.samples <flowbio.v2.Client.samples>`.

List sample types, metadata attributes, organisms, and projects::

    sample_types = client.samples.get_types()
    attributes = client.samples.get_metadata_attributes()
    organisms = client.samples.get_organisms()
    projects = client.samples.get_owned_projects()

Upload with metadata, project, and organism::

    from pathlib import Path

    sample = client.samples.upload_sample(
        name="Paired-end Sample",
        sample_type="RNA-Seq",
        data={
            "reads1": Path("R1.fastq.gz"),
            "reads2": Path("R2.fastq.gz"),
        },
        metadata={"strandedness": "reverse"},
        project_id="proj_123",
        organism_id="org_456",
    )
"""
from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel
from tqdm import tqdm

from flowbio.v2._pagination import PageIterator
from flowbio.v2.exceptions import AnnotationValidationError, BadRequestError

if TYPE_CHECKING:
    from flowbio.v2.client import ClientConfig
    from flowbio.v2._transport import HttpTransport


class SampleType(BaseModel, frozen=True):
    """A type of sample that can be uploaded to the Flow platform.

    :param identifier: Unique identifier for this sample type.
    :param name: Human-readable display name.
    :param description: Explanation of what this sample type represents.

    Example::

        sample_types = client.samples.get_types()
        for st in sample_types:
            print(f"{st.identifier}: {st.name}")
    """

    identifier: str
    name: str
    description: str


class MetadataAttribute(BaseModel, frozen=True):
    """A metadata attribute that can be attached to a sample. See :ref:`metadata-attributes` for a more detailed
    explanation.

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

    :param id: Unique identifier for this project.
    :param name: Human-readable display name.
    :param description: Explanation of what this project is for.

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

    :param id: Unique identifier for this organism.
    :param name: Common name.
    :param latin_name: Scientific (Latin) name.

    Example::

        organisms = client.samples.get_organisms()
        for o in organisms:
            print(f"{o.id}: {o.name} ({o.latin_name})")
    """

    id: str
    name: str
    latin_name: str


class Sample(BaseModel, frozen=True):
    """A sample on the Flow platform. For now this only includes id, but when we
    add more methods to retrieve samples with more detail, more fields will be added.


    :param id: The unique identifier of the sample.
    """

    id: str


class MultiplexedUpload(BaseModel, frozen=True):
    """Result of a multiplexed data upload.

    :param data_ids: IDs for the uploaded multiplexed reads data.
    :param annotation_id: ID for the uploaded annotation data.
    :param warnings: Annotation warnings returned by the server.
        Empty if the annotation was accepted without warnings.
    """

    data_ids: list[str]
    annotation_id: str
    warnings: list[dict]


class SampleResource:
    """Provides access to sample-related API endpoints.

    Accessed via :attr:`Client.samples`::

        client = Client()
        sample_types = client.samples.get_types()
    """

    def __init__(self, transport: HttpTransport, config: ClientConfig) -> None:
        self._transport = transport
        self._config = config

    def upload_sample(
        self,
        name: str,
        sample_type: str,
        data: dict[str, Path],
        metadata: dict[str, str] | None = None,
        project_id: str | None = None,
        organism_id: str | None = None,
    ) -> Sample:
        """Upload a sample with one or more files.

        Multiple files are linked together into a single sample. Chunk size and progress display
        are controlled via :class:`flowbio.v2.ClientConfig`.

        Requires authentication.

        Example::

            from pathlib import Path

            result = client.samples.upload_sample(
                name="My RNA-Seq Sample",
                sample_type="RNA-Seq",
                data={"reads1": Path("reads_R1.fastq.gz")},
                metadata={"strandedness": "forward"},
            )
            print(f"Sample ID: {result.sample_id}")

        :param name: The name of the sample.
        :param sample_type: The sample type identifier
            (e.g. ``"RNA-Seq"``). This must be a valid sample type specified in the Flow application. You can get valid
            sample types from :meth:`get_types`.
        :param data: A mapping of data type identifiers to file paths.
            For sequencing samples, use ``reads1`` and optionally
            ``reads2`` — these are the only valid reads keys, and
            ``reads1`` is always uploaded first::

                # Single-end
                {"reads1": Path("sample.fastq.gz")}

                # Paired-end
                {"reads1": Path("R1.fastq.gz"), "reads2": Path("R2.fastq.gz")}

            For non-sequencing sample types, any key names are
            accepted and files are uploaded in the order given::

                {"input": Path("counts.csv")}

        :param metadata: Optional metadata key-value pairs. See
            :ref:`metadata-attributes` for details on required attributes.
        :param project_id: Optional project ID to assign the sample to. This must be a project you own. You can see
            available projects by calling :meth:`get_owned_projects`.
        :param organism_id: Optional organism ID to associate with.
        :raises ValueError: If reads keys are invalid (e.g. ``reads3``)
            or ``reads2`` is provided without ``reads1``.
        :raises FlowApiError: If any of the data is invalid, e.g. sample_type doesn't exist or missing required
            metadata attributes.
        """
        files = self._ordered_files(data)
        previous_data_ids: list[str] = []
        result: dict = {}
        for file_index, (data_type, file_path) in enumerate(files):
            is_last_file = file_index == len(files) - 1
            fields = self._build_sample_fields(
                name, sample_type, metadata, project_id, organism_id,
            )
            result = self._upload_in_chunks(
                "/upload/sample",
                file_path,
                extra_fields={
                    "is_last_sample": is_last_file,
                    "previous_data": previous_data_ids,
                    **(fields or {}),
                },
            )
            if not is_last_file:
                previous_data_ids.append(result["data_id"])
        return Sample(id=result["sample_id"])

    def upload_multiplexed_data(
        self,
        reads: dict[str, Path],
        annotation: Path,
        ignore_warnings: bool = True,
    ) -> MultiplexedUpload:
        """Upload multiplexed reads and an annotation sheet.

        Validates and uploads the annotation sheet first, so that reads
        files are not uploaded if the annotation is invalid. Then uploads
        one or two reads files to ``/upload/multiplexed``.

        By default, annotation warnings are automatically accepted (the
        upload is retried with ``ignore_warnings=True``) and included in
        the result for inspection. Set ``ignore_warnings=False`` to
        reject the upload on warnings instead.

        Requires authentication.

        Example::

            from pathlib import Path

            result = client.samples.upload_multiplexed_data(
                reads={"reads1": Path("multiplexed_R1.fastq.gz")},
                annotation=Path("annotation.xlsx"),
            )
            print(f"Data IDs: {result.data_ids}")
            print(f"Annotation ID: {result.annotation_id}")
            if result.warnings:
                print(f"Warnings: {result.warnings}")

        :param reads: A mapping of reads keys to file paths. Use
            ``reads1`` for single-end, or ``reads1`` and ``reads2`` for
            paired-end. ``reads1`` is always uploaded first::

                # Single-end
                {"reads1": Path("multiplexed.fastq.gz")}

                # Paired-end
                {"reads1": Path("R1.fastq.gz"), "reads2": Path("R2.fastq.gz")}

        :param annotation: Path to the annotation sheet (``.xlsx`` or
            ``.csv``). Use :meth:`get_annotation_template` to download a
            template.
        :param ignore_warnings: If ``True`` (the default), annotation
            warnings are automatically accepted and included in the
            result. If ``False``, warnings cause a
            :class:`BadRequestError` to be raised.
        :raises ValueError: If reads keys are invalid (e.g. ``reads3``)
            or ``reads2`` is provided without ``reads1``.
        :raises AnnotationValidationError: If the annotation has hard
            validation errors that cannot be ignored.
        :raises BadRequestError: If ``ignore_warnings=False`` and the
            annotation has warnings.
        """
        files = self._ordered_files(reads)

        annotation_id, warnings = self._upload_annotation(
            annotation, ignore_warnings,
        )

        data_ids: list[str] = []
        for _, file_path in files:
            extra_fields = {"reads1": data_ids[0]} if data_ids else {}
            result = self._upload_in_chunks(
                "/upload/multiplexed", file_path, extra_fields,
            )
            data_ids.append(result["id"])

        return MultiplexedUpload(
            data_ids=data_ids,
            annotation_id=annotation_id,
            warnings=warnings,
        )

    def get_annotation_template(self, sample_type: str = "generic") -> bytes:
        """Download an annotation sheet template for multiplexed uploads.

        Annotation sheets are spreadsheets that describe multiple samples
        in a single file. Download a template, fill in one row per sample
        with names, file paths, and metadata, then submit the completed
        sheet to upload all samples in one batch.

        A type-specific template (e.g. ``"rna_seq"``) includes columns
        for metadata attributes relevant to that sample type. The
        ``"generic"`` template includes only the base columns shared by
        all types.

        Returns the raw xlsx bytes. Write them to disk to get a usable
        spreadsheet::

            from pathlib import Path

            template = client.samples.get_annotation_template("rna_seq")
            Path("template.xlsx").write_bytes(template)

        :param sample_type: The sample type identifier (e.g. ``"rna_seq"``).
            Defaults to ``"generic"`` for a universal template. See
            :meth:`get_types` for available sample types.
        :returns: The raw xlsx file bytes.
        :raises NotFoundError: If the sample type does not exist.
        """
        return self._transport.get_bytes(f"/annotation/{sample_type}")

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
        """Return the available metadata attributes for samples. See :ref:`metadata-attributes` for more detail.

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

    def _upload_in_chunks(
        self,
        endpoint: str,
        file_path: Path,
        extra_fields: dict | None = None,
    ) -> dict:
        chunk_size = self._config.chunk_size
        file_size = file_path.stat().st_size
        num_chunks = max(1, math.ceil(file_size / chunk_size))
        data_id: str | None = None
        result: dict = {}
        chunks = range(num_chunks)
        if self._config.show_progress:
            chunks = tqdm(
                chunks,
                desc=f"Uploading {file_path.name}",
                unit="chunk",
            )
        for chunk_index in chunks:
            is_last_chunk = chunk_index == num_chunks - 1
            form_data: dict[str, str] = {
                "filename": file_path.name,
                "expected_file_size": str(chunk_index * chunk_size),
                "is_last": is_last_chunk,
                "data": data_id,
                **(extra_fields or {}),
            }
            with open(file_path, "rb") as f:
                f.seek(chunk_index * chunk_size)
                chunk = f.read(chunk_size)
            result = self._transport.post(
                endpoint,
                data=form_data,
                files={"blob": (file_path.name, chunk, "application/octet-stream")},
            )
            data_id = result.get("data_id") or result.get("id")
        return result

    def _upload_annotation(
        self, file_path: Path, ignore_warnings: bool,
    ) -> tuple[str, list[dict]]:
        try:
            result = self._upload_in_chunks("/upload/annotation", file_path)
            return result["id"], []
        except BadRequestError as e:
            if isinstance(e.message, dict) and "validation" in e.message:
                raise AnnotationValidationError(errors=e.message["validation"]) from e
            if isinstance(e.message, dict) and "warnings" in e.message:
                if not ignore_warnings:
                    raise AnnotationValidationError(
                        errors=e.message["warnings"],
                    ) from e
                warnings = e.message["warnings"]
                result = self._upload_in_chunks(
                    "/upload/annotation",
                    file_path,
                    extra_fields={"ignore_warnings": True},
                )
                return result["id"], warnings
            raise

    _VALID_READS_KEYS = {"reads1", "reads2"}

    @staticmethod
    def _ordered_files(data: dict[str, Path]) -> list[tuple[str, Path]]:
        has_reads_keys = any(k.startswith("reads") for k in data)
        if not has_reads_keys:
            return list(data.items())
        invalid = set(data.keys()) - SampleResource._VALID_READS_KEYS
        if invalid:
            raise ValueError(
                f"Invalid reads key(s): {invalid}. "
                f"Valid keys are: {SampleResource._VALID_READS_KEYS}"
            )
        if "reads2" in data and "reads1" not in data:
            raise ValueError("reads1 is required when reads2 is provided")
        return sorted(data.items(), key=lambda item: item[0])

    @staticmethod
    def _build_sample_fields(
        name: str,
        sample_type: str,
        metadata: dict[str, str] | None,
        project_id: str | None,
        organism_id: str | None,
    ) -> dict[str, str]:
        fields: dict[str, str] = {
            "sample_name": name,
            "sample_type": sample_type,
        }
        if metadata:
            fields.update(metadata)
        if project_id:
            fields["project"] = project_id
        if organism_id:
            fields["organism"] = organism_id
        return fields

    def _resolve_options(self, item: dict) -> list[str] | None:
        if item.get("allow_user_terms"):
            return None
        if not item.get("has_options"):
            return None
        options_response = self._transport.get(
            f"/samples/metadata/{item['identifier']}/options",
        )
        return [opt["value"] for opt in options_response["options"]]
