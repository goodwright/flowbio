"""
Generic data-file operations are accessed via
:attr:`Client.data <flowbio.v2.Client.data>`.

Upload a data file::

    from pathlib import Path
    from flowbio.v2 import Client, TokenCredentials

    client = Client()
    client.log_in(TokenCredentials(token))

    data = client.data.upload_data(Path("counts.tsv"))
    print(data.id)
"""
from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field

if TYPE_CHECKING:
    from flowbio.v2._uploads import ChunkedUploader


class Data(BaseModel, frozen=True):
    """A data file on the Flow platform. For now this only includes id, but
    when we add methods to retrieve data files with more detail, more fields
    will be added.
    """

    id: str = Field(description="The unique identifier of the data file.")


class DataResource:
    """Provides access to generic data-file API endpoints.

    Accessed via :attr:`Client.data`::

        client = Client()
        data = client.data.upload_data(Path("counts.tsv"))
    """

    def __init__(self, uploader: ChunkedUploader) -> None:
        self._uploader = uploader

    def upload_data(
        self,
        path: Path,
        filename: str | None = None,
        data_type: str | None = None,
        is_directory: bool = False,
    ) -> Data:
        """Upload a generic data file to the Flow platform.

        Uploads the file in chunks (chunk size and progress display are
        controlled via :class:`flowbio.v2.ClientConfig`) and returns the
        created data file.

        Requires authentication.

        Example::

            from pathlib import Path

            data = client.data.upload_data(Path("counts.tsv"))
            print(f"Data ID: {data.id}")

        :param path: The local file to upload.
        :param filename: Optional override for the name the file is stored
            under on Flow. Defaults to ``path.name``. Useful when reading
            from a local path but storing under a different name. Must
            contain no spaces — the server rejects spaces with a
            :class:`BadRequestError`.
        :param data_type: Optional ``DataType`` identifier. Validated
            server-side only; an invalid value raises a
            :class:`BadRequestError`.
        :param is_directory: When ``True``, the server treats the upload as
            an archive and unpacks it. ``path`` must then point at a
            ``.zip``/``.tar``/``.tar.gz``.
        :returns: The created :class:`Data`.
        :raises BadRequestError: If the filename contains spaces or
            ``data_type`` is invalid.
        :raises AuthenticationError: If the request is unauthenticated.
        """
        extra_fields: dict[str, str | bool] = {}
        if data_type is not None:
            extra_fields["data_type"] = data_type
        if is_directory:
            extra_fields["is_directory"] = True
        result = self._uploader.upload_in_chunks(
            "/upload", path, extra_fields, filename=filename,
        )
        return Data(id=result["id"])
