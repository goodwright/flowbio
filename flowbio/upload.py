"""Logic for uploading data to Flow."""

import os
import io
import math
import base64
import warnings

import requests
from tqdm import tqdm
from pathlib import Path
from .queries import DATA
from .mutations import UPLOAD_DATA, UPLOAD_ANNOTATION, UPLOAD_MULTIPLEXED
from flowbio.v2.auth import TokenCredentials
from flowbio.v2.client import Client as V2Client, ClientConfig

class TempFile(io.BytesIO):
    def __init__(self, *args, name="", **kwargs):
        self.name = name
        io.BytesIO.__init__(self, *args, **kwargs)



class UploadClient:

    def data(self, id):
        """Returns a data object.
        
        :param str id: The ID of the data.
        :rtype: ``dict``"""

        return self.execute(DATA, variables={"id": id})["data"]["data"]
    

    def upload_data(self, path, chunk_size=1_000_000, progress=False, use_base64=False, retries=0):
        """Uploads a file to the server.
        
        :param str path: The path to the file.
        :param int chunk_size: The size of each chunk to upload.
        :param bool progress: Whether to show a progress bar."""

        size = os.path.getsize(path)
        chunks = math.ceil(size / chunk_size)
        data_id = None
        chunk_nums = tqdm(range(chunks)) if progress else range(chunks)
        for chunk_num in chunk_nums:
            filename = Path(path).name
            if progress: chunk_nums.set_description(f"Uploading {filename}")
            with open(path, "rb") as f:
                f.seek(chunk_num * chunk_size)
                data = f.read(chunk_size)
                if use_base64: data = base64.b64encode(data)
                data = TempFile(data, name=filename)
                resp = self.execute(UPLOAD_DATA, retries=retries, variables={
                    "blob": data,
                    "isLast": chunk_num == chunks - 1,
                    "expectedFileSize": chunk_num * chunk_size,
                    "data": data_id,
                    "filename": filename
                })
                data_id = resp["data"]["uploadData"]["dataId"]
        return self.data(data_id)

    @warnings.deprecated("Being phased out. Use `flowbio.v2.Client.upload_sample` instead.")
    def upload_sample(
        self,
        name: str,
        path1: str,
        path2: str | None = None,
        chunk_size: int = 1_000_000,
        progress: bool = False,
        metadata: dict | None = None,
        use_base64: bool = False,
    ) -> dict:
        """Uploads a sample to the server.

        :param name: The name of the sample.
        :param path1: The path to the first file.
        :param path2: The path to the second file if sample is paired-end.
        :param chunk_size: The size of each chunk to upload.
        :param progress: Whether to show a progress bar.
        :param metadata: The metadata to attach to the sample. This must
            include a ``sample_type`` key. May also include ``project`` and
            ``organism`` keys, which are extracted and passed as dedicated
            parameters to the v2 client.
        """

        v2_client = V2Client(
            base_url=self.url.replace("/graphql", ""),
            config=ClientConfig(chunk_size=chunk_size, show_progress=progress),
        )
        v2_client.log_in(TokenCredentials(self.headers["Authorization"]))

        data = {"reads1": Path(path1)}
        if path2:
            data["reads2"] = Path(path2)

        metadata = dict(metadata) if metadata else {}
        sample_type = metadata.pop("sample_type")
        project_id = metadata.pop("project", None)
        organism_id = metadata.pop("organism", None)

        result = v2_client.samples.upload_sample(
            name=name,
            sample_type=sample_type,
            data=data,
            metadata=metadata or None,
            project_id=project_id,
            organism_id=organism_id,
        )
        return self.sample(result.id)


    def upload_annotation(self, path, ignore_warnings=False, chunk_size=1_000_000, progress=False, use_base64=False, retries=0):
        """Uploads an annotation sheet to the server.

        :param str path: The path to the annotation sheet.
        :param bool ignore_warnings: Whether to ignore warnings.
        :param int chunk_size: The size of each chunk to upload.
        :param bool progress: Whether to show a progress bar.
        :param int retries: The number of times to retry the upload.
        :rtype: ``dict``"""

        size = os.path.getsize(path)
        chunks = math.ceil(size / chunk_size)
        data_id = None
        chunk_nums = tqdm(range(chunks)) if progress else range(chunks)
        for chunk_num in chunk_nums:
            filename = Path(path).name
            if progress: chunk_nums.set_description(f"Uploading {filename}")
            with open(path, "rb") as f:
                f.seek(chunk_num * chunk_size)
                data = f.read(chunk_size)
                if use_base64: data = base64.b64encode(data)
                data = TempFile(data, name=filename)
                resp = self.execute(UPLOAD_ANNOTATION, retries=retries, variables={
                    "blob": data,
                    "isLast": chunk_num == chunks - 1,
                    "expectedFileSize": chunk_num * chunk_size,
                    "data": data_id,
                    "ignoreWarnings": ignore_warnings,
                    "filename": filename
                })
                data_id = resp["data"]["uploadAnnotationData"]["dataId"]
        return self.data(data_id)


    def upload_multiplexed(self, path, chunk_size=1_000_000, progress=False, use_base64=False, retries=0):
        """Uploads a multiplexed reads file to the server.

        :param str path: The path to the multiplexed reads file.
        :param int chunk_size: The size of each chunk to upload.
        :param bool progress: Whether to show a progress bar.
        :param int retries: The number of times to retry the upload.
        :rtype: ``dict``"""
        
        size = os.path.getsize(path)
        chunks = math.ceil(size / chunk_size)
        data_id = None
        chunk_nums = tqdm(range(chunks)) if progress else range(chunks)
        for chunk_num in chunk_nums:
            filename = Path(path).name
            if progress: chunk_nums.set_description(f"Uploading {filename}")
            with open(path, "rb") as f:
                f.seek(chunk_num * chunk_size)
                data = f.read(chunk_size)
                if use_base64: data = base64.b64encode(data)
                data = TempFile(data, name=filename)
                resp = self.execute(UPLOAD_MULTIPLEXED, retries=retries, variables={
                    "blob": data,
                    "isLast": chunk_num == chunks - 1,
                    "expectedFileSize": chunk_num * chunk_size,
                    "data": data_id,
                    "filename": filename
                })
                data_id = resp["data"]["uploadMultiplexedData"]["dataId"]
        return self.data(data_id)