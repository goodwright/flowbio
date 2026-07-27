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

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Literal, NewType

from pydantic import BaseModel, Field, field_validator

from flowbio.v2._pagination import PageIterator
from flowbio.v2.exceptions import (
    AnnotationValidationError,
    BadRequestError,
)

if TYPE_CHECKING:
    from flowbio.v2._transport import HttpTransport
    from flowbio.v2._uploads import ChunkedUploader


SampleTypeId = NewType("SampleTypeId", str)
"""The identifier of a sample type (e.g. ``"RNA-Seq"``), as listed by
:meth:`SampleResource.get_types`."""


class SampleType(BaseModel, frozen=True):
    """A type of sample that can be uploaded to the Flow platform.

    Example::

        sample_types = client.samples.get_types()
        for st in sample_types:
            print(f"{st.identifier}: {st.name}")
    """

    identifier: SampleTypeId = Field(description="Unique identifier for this sample type.")
    name: str = Field(description="Human-readable display name.")
    description: str = Field(description="Explanation of what this sample type represents.")


class MetadataAttribute(BaseModel, frozen=True):
    """A metadata attribute that can be attached to a sample. See :ref:`metadata-attributes` for a more detailed
    explanation.

    Example::

        attributes = client.samples.get_metadata_attributes()
        for attr in attributes:
            if attr.options is not None:
                print(f"{attr.name}: choose from {attr.options}")
    """

    identifier: str = Field(description="Unique identifier for this attribute.")
    name: str = Field(description="Human-readable display name.")
    description: str = Field(description="Explanation of what this attribute represents.")
    required: bool = Field(description="Whether this attribute is required at sample creation.")
    required_for_sample_types: list[SampleTypeId] = Field(
        description="Sample type identifiers for which this attribute is required at creation.",
    )
    options: list[str] | None = Field(
        description="The list of valid values, or ``None`` if any value is accepted.",
    )
    allow_annotation: bool = Field(
        default=False,
        description="Whether this attribute permits a free-text annotation companion value.",
    )


class Project(BaseModel, frozen=True):
    """A project that samples can be assigned to.

    Example::

        projects = client.samples.get_owned_projects()
        for p in projects:
            print(f"{p.id}: {p.name}")
    """

    id: str = Field(description="Unique identifier for this project.")
    name: str = Field(description="Human-readable display name.")
    description: str = Field(description="Explanation of what this project is for.")


class Organism(BaseModel, frozen=True):
    """An organism that a sample can be associated with.

    Example::

        organisms = client.samples.get_organisms()
        for o in organisms:
            print(f"{o.id}: {o.name} ({o.latin_name})")
    """

    id: str = Field(description="Unique identifier for this organism.")
    name: str = Field(description="Common name.")
    latin_name: str = Field(description="Scientific (Latin) name.")


class Sample(BaseModel, frozen=True):
    """A sample on the Flow platform. For now this only includes id, but when we
    add more methods to retrieve samples with more detail, more fields will be added.
    """

    id: str = Field(description="The unique identifier of the sample.")


class MultiplexedUpload(BaseModel, frozen=True):
    """Result of a multiplexed data upload."""

    data_ids: list[str] = Field(description="IDs for the uploaded multiplexed reads data.")
    annotation_id: str = Field(description="ID for the uploaded annotation data.")
    warnings: list[dict] = Field(
        description="Annotation warnings returned by the server. Empty if the annotation was accepted without warnings.",
    )


SampleImportJobId = NewType("SampleImportJobId", int)
"""The identifier of a sample-import job, as returned by
:meth:`SampleResource.import_samples`."""


SampleImportStatus = Literal["RUNNING", "COMPLETED", "FAILED"]
"""The lifecycle state of a :class:`SampleImportJob`."""


@dataclass(frozen=True)
class SampleImportSpec:
    """One accession to import, with its per-accession identity and metadata.

    Example::

        specs = [
            SampleImportSpec(accession="ERR1160845", sample_type="RNA-Seq"),
            SampleImportSpec(
                accession="ERR10677146",
                sample_type="RNA-Seq",
                organism_id="Hs",
                metadata={"strandedness": "reverse"},
            ),
        ]

    :param accession: The public-repository run or experiment accession
        (e.g. ``"ERR1160845"``), validated server-side.
    :param sample_type: The sample type identifier (e.g. ``"RNA-Seq"``),
        validated server-side. See :meth:`SampleResource.get_types`.
    :param name: Optional sample name. Defaults to ``accession`` server-side
        when omitted.
    :param organism_id: Optional organism id (e.g. ``"Hs"``) to associate
        with the sample, sent as ``organism``.
    :param metadata: Optional metadata key-value pairs. See
        :ref:`metadata-attributes` for details on required attributes.
    """

    accession: str
    sample_type: SampleTypeId
    name: str | None = None
    organism_id: str | None = None
    metadata: dict[str, str] | None = None


class SampleImportJob(BaseModel, frozen=True):
    """A batch job that imports one or more accessions into samples.

    All accessions submitted in one :meth:`SampleResource.import_samples` call
    share a single job: ``status`` and ``error`` describe the whole batch, and
    ``accessions``/``sample_ids`` correspond positionally once ``status`` is
    ``"COMPLETED"``.
    """

    id: SampleImportJobId = Field(description="Unique identifier for this import job.")
    status: SampleImportStatus = Field(description="The job's current lifecycle state.")
    created: datetime | None = Field(default=None, description="When the job was created.")
    started: datetime | None = Field(default=None, description="When the job started running, if it has.")
    finished: datetime | None = Field(
        default=None, description="When the job finished (completed or failed), if it has.",
    )
    accessions: list[str] = Field(
        default_factory=list, description="The accessions submitted with this job, in submission order.",
    )
    sample_ids: list[int] = Field(
        default_factory=list,
        description="The created samples' ids, corresponding to ``accessions`` once the job has completed.",
    )
    execution_id: int | None = Field(
        default=None, description="The pipeline execution backing this job, if one was created.",
    )
    error: str | None = Field(
        default=None, description='The failure reason, set only when status is "FAILED".',
    )

    @field_validator("created", "started", "finished", mode="after")
    @classmethod
    def _normalize_to_utc(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        # A naive value (no tzinfo) is treated as already UTC, matching what
        # the server always means by these timestamps, rather than left
        # ambiguous for every consumer (CLI, --json, library) to decide on
        # its own.
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)


class SampleResource:
    """Provides access to sample-related API endpoints.

    Accessed via :attr:`Client.samples`::

        client = Client()
        sample_types = client.samples.get_types()
    """

    def __init__(self, transport: HttpTransport, uploader: ChunkedUploader) -> None:
        self._transport = transport
        self._uploader = uploader

    def upload_sample(
        self,
        name: str,
        sample_type: SampleTypeId,
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
            print(f"Sample ID: {result.id}")

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
            result = self._uploader.upload_in_chunks(
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
        :raises AnnotationValidationError: If ``ignore_warnings=False``
            and the annotation has warnings.
        """
        files = self._ordered_files(reads)

        annotation_id, warnings = self._upload_annotation(
            annotation, ignore_warnings,
        )

        data_ids: list[str] = []
        for _, file_path in files:
            extra_fields = {"reads1": data_ids[0]} if data_ids else {}
            result = self._uploader.upload_in_chunks(
                "/upload/multiplexed", file_path, extra_fields,
            )
            data_ids.append(result["id"])

        return MultiplexedUpload(
            data_ids=data_ids,
            annotation_id=annotation_id,
            warnings=warnings,
        )

    def get_annotation_template(
        self, sample_type: SampleTypeId = SampleTypeId("generic"),
    ) -> bytes:
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

    def import_samples(self, imports: Sequence[SampleImportSpec]) -> SampleImportJob:
        """Kick off a batch import of samples from public-repository accessions.

        Every accession is submitted together and tracked as a single job — poll
        it with :meth:`get_import` until its status leaves ``"RUNNING"``.

        Requires authentication.

        Example::

            job = client.samples.import_samples([
                SampleImportSpec(accession="ERR1160845", sample_type="RNA-Seq"),
            ])
            print(f"Import job: {job.id}")

        :param imports: The accessions to import, one :class:`SampleImportSpec` each.
        :raises FlowApiError: If any entry is invalid, e.g. an unsupported
            accession format, unknown sample type, or missing required metadata.
        """
        payload = {"imports": [self._import_spec_fields(spec) for spec in imports]}
        return SampleImportJob(**self._transport.post("/v2/sample-imports", json=payload))

    def get_import(self, job_id: SampleImportJobId) -> SampleImportJob:
        """Fetch the current state of an import job.

        Example::

            job = client.samples.get_import(job.id)
            if job.status == "COMPLETED":
                print(f"Imported samples: {job.sample_ids}")

        :param job_id: The job id returned by :meth:`import_samples`.
        :raises NotFoundError: If no import job with that id exists.
        """
        return SampleImportJob(**self._transport.get(f"/v2/sample-imports/{job_id}"))

    @staticmethod
    def _import_spec_fields(spec: SampleImportSpec) -> dict:
        fields: dict = {"accession": spec.accession, "sample_type": spec.sample_type}
        if spec.name is not None:
            fields["name"] = spec.name
        if spec.organism_id is not None:
            fields["organism"] = spec.organism_id
        if spec.metadata:
            fields["metadata"] = spec.metadata
        return fields

    def _create_metadata_attribute(self, item: dict) -> MetadataAttribute:
        item["required_for_sample_types"] = [
            SampleTypeId(link["sample_type_identifier"])
            for link in item.get("sample_type_links", [])
            if link.get("required")
        ]
        item["options"] = self._resolve_options(item)
        return MetadataAttribute(**item)

    def _upload_annotation(
        self, file_path: Path, ignore_warnings: bool,
    ) -> tuple[str, list[dict]]:
        try:
            result = self._uploader.upload_in_chunks("/upload/annotation", file_path)
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
                result = self._uploader.upload_in_chunks(
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
        sample_type: SampleTypeId,
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
