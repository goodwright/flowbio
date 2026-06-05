"""Shared chunked-upload mechanics for the v2 resources.

The Flow upload endpoints (``/upload``, ``/upload/sample``,
``/upload/multiplexed``, ``/upload/annotation``) all speak the same
chunked multipart protocol: each chunk is POSTed with a byte-offset, the
server returns an id, and that id is threaded into the next chunk. This
module owns that protocol so every resource shares one implementation.
"""
from __future__ import annotations

import math
from http import HTTPStatus
from pathlib import Path
from typing import TYPE_CHECKING

import httpx
from tenacity import (
    Retrying,
    retry_if_exception,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)
from tqdm import tqdm

from flowbio.v2.exceptions import FlowApiError

if TYPE_CHECKING:
    from flowbio.v2.client import ClientConfig
    from flowbio.v2._transport import HttpTransport

_RETRYABLE_STATUS_CODES = frozenset({
    HTTPStatus.BAD_GATEWAY,
    HTTPStatus.SERVICE_UNAVAILABLE,
    HTTPStatus.GATEWAY_TIMEOUT,
})


def _is_retryable_api_error(exc: BaseException) -> bool:
    return (
        isinstance(exc, FlowApiError)
        and exc.status_code in _RETRYABLE_STATUS_CODES
    )


class ChunkedUploader:
    """Uploads a file to a Flow upload endpoint in chunks.

    Constructed with the shared transport and client config, and reused by
    every resource that needs to upload files (samples, generic data, ...).
    Chunk size, progress display, and retry behaviour are all read from the
    :class:`flowbio.v2.ClientConfig`.
    """

    def __init__(self, transport: HttpTransport, config: ClientConfig) -> None:
        self._transport = transport
        self._config = config

    def upload_in_chunks(
        self,
        endpoint: str,
        file_path: Path,
        extra_fields: dict | None = None,
        filename: str | None = None,
    ) -> dict:
        """Upload ``file_path`` to ``endpoint`` in chunks and return the final response.

        :param endpoint: The upload endpoint (e.g. ``"/upload"``).
        :param file_path: The local file to read chunk bytes from.
        :param extra_fields: Extra multipart form fields sent with every chunk.
        :param filename: The name the file is stored under. Defaults to
            ``file_path.name``. When provided it sets the multipart
            ``filename`` form field (which the backend treats as
            authoritative) and the blob tuple's filename.
        """
        stored_filename = filename or file_path.name
        chunk_size = self._config.chunk_size
        file_size = file_path.stat().st_size
        num_chunks = max(1, math.ceil(file_size / chunk_size))
        data_id: str | None = None
        result: dict = {}
        chunks = range(num_chunks)
        if self._config.show_progress:
            chunks = tqdm(
                chunks,
                desc=f"Uploading {stored_filename}",
                unit="chunk",
            )
        with open(file_path, "rb") as f:
            for chunk_index in chunks:
                is_last_chunk = chunk_index == num_chunks - 1
                form_data: dict[str, str | bool | list[str] | None] = {
                    "filename": stored_filename,
                    # API uses this as a byte offset to verify upload resumption
                    "expected_file_size": str(chunk_index * chunk_size),
                    "is_last": is_last_chunk,
                    "data": data_id,
                    **(extra_fields or {}),
                }
                chunk = f.read(chunk_size)
                result = self._post_chunk_with_retry(
                    endpoint,
                    data=form_data,
                    files={"blob": (stored_filename, chunk, "application/octet-stream")},
                )
                data_id = result.get("data_id") or result.get("id")
        return result

    def _post_chunk_with_retry(self, endpoint: str, data: dict, files: dict) -> dict:
        retryer = Retrying(
            retry=(
                retry_if_exception_type((httpx.ReadTimeout, httpx.WriteTimeout))
                | retry_if_exception(_is_retryable_api_error)
            ),
            stop=stop_after_attempt(self._config.upload_retries + 1),
            wait=wait_exponential(multiplier=1, max=60),
            reraise=True,
        )
        return retryer(self._transport.post, endpoint, data=data, files=files)
