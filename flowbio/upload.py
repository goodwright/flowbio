"""Logic for uploading data to Flow."""

import io
import os
import io
import math
from tqdm import tqdm
from pathlib import Path
from .queries import DATA, SAMPLE
from .mutations import UPLOAD_DATA, UPLOAD_SAMPLE

class TempFile(io.BytesIO):
    def __init__(self, *args, name="", **kwargs):
        self.name = name
        io.BytesIO.__init__(self, *args, **kwargs)



class UploadClient:

    def data(self, id):
        """Returns a data object."""
        
        return self.execute(DATA, variables={"id": id})["data"]["data"]
    

    def upload(self, path, chunk_size=1_000_000, progress=False):
        """Uploads a file to the server."""

        size = os.path.getsize(path)
        chunks = math.ceil(size / chunk_size)
        data_id = None
        chunk_nums = tqdm(range(chunks)) if progress else range(chunks)
        for chunk_num in chunk_nums:
            filename = Path(path).name
            if progress:
                chunk_nums.set_description(f"Uploading {filename}")
            with open(path, "rb") as f:
                f.seek(chunk_num * chunk_size)
                data = TempFile(f.read(chunk_size), name=filename)
                resp = self.execute(UPLOAD_DATA, variables={
                    "blob": data,
                    "isLast": chunk_num == chunks - 1,
                    "expectedFileSize": chunk_num * chunk_size,
                    "data": data_id,
                    "filename": filename
                })
                data_id = resp["data"]["uploadData"]["dataId"]
        return self.data(data_id)


    def upload_sample(self, name, path1, path2=None, chunk_size=1_000_000, progress=False, metadata=None):
        """Uploads a sample to the server."""

        reads = [path1, path2] if path2 else [path1]
        previous_data = []
        data_id, sample_id = None, None
        metadata = metadata or {}
        for path in reads:
            size = os.path.getsize(path)
            chunks = math.ceil(size / chunk_size)
            chunk_nums = tqdm(range(chunks)) if progress else range(chunks)
            for chunk_num in chunk_nums:
                filename = Path(path).name
                if progress:
                    chunk_nums.set_description(f"Uploading {filename}")
                with open(path, "rb") as f:
                    f.seek(chunk_num * chunk_size)
                    data = TempFile(f.read(chunk_size), name=filename)
                    is_last_data = chunk_num == chunks - 1
                    is_last_sample = is_last_data and path == reads[-1]
                    resp = self.execute(UPLOAD_SAMPLE, variables={
                        "blob": data,
                        "isLastData": is_last_data,
                        "isLastSample": is_last_sample,
                        "expectedFileSize": chunk_num * chunk_size,
                        "data": data_id,
                        "filename": filename,
                        "sampleName": name,
                        "previousData": previous_data,
                        **metadata
                    })
                    if "errors" in resp:
                        raise Exception(resp["errors"])
                    data_id = resp["data"]["uploadDemultiplexedData"]["dataId"]
                    sample_id = resp["data"]["uploadDemultiplexedData"]["sampleId"]
                    if is_last_data:
                        previous_data.append(data_id)
                        data_id = None
        sample = self.execute(SAMPLE, variables={"id": sample_id})["data"]["sample"]   
        return sample