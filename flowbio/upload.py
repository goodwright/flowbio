"""Logic for uploading data to Flow."""

import io
import os
import io
import math
import base64
from tqdm import tqdm
from pathlib import Path
from .queries import DATA
from .mutations import UPLOAD_DATA, UPLOAD_SAMPLE, UPLOAD_ANNOTATION, UPLOAD_MULTIPLEXED

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
    

    def upload_data(self, path, chunk_size=1_000_000, progress=False, use_base64=True):
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
                resp = self.execute(UPLOAD_DATA, variables={
                    "blob": data,
                    "isLast": chunk_num == chunks - 1,
                    "expectedFileSize": chunk_num * chunk_size,
                    "data": data_id,
                    "filename": filename
                })
                data_id = resp["data"]["uploadData"]["dataId"]
        return self.data(data_id)


    def upload_sample(self, name, path1, path2=None, chunk_size=1_000_000, progress=False, metadata=None, use_base64=True):
        """Uploads a sample to the server.
        
        :param str name: The name of the sample.
        :param str path1: The path to the first file.
        :param str path2: The path to the second file if sample is paired-end.
        :param int chunk_size: The size of each chunk to upload.
        :param bool progress: Whether to show a progress bar.
        :param dict metadata: The metadata to attach to the sample.
        :rtype: ``dict``"""

        reads = [path1, path2] if path2 else [path1]
        data_id, sample_id, previous_data = None, None, []
        for path in reads:
            size = os.path.getsize(path)
            chunks = math.ceil(size / chunk_size)
            chunk_nums = tqdm(range(chunks)) if progress else range(chunks)
            for chunk_num in chunk_nums:
                filename = Path(path).name
                if progress: chunk_nums.set_description(f"Uploading {filename}")
                with open(path, "rb") as f:
                    f.seek(chunk_num * chunk_size)
                    data = f.read(chunk_size)
                    if use_base64: data = base64.b64encode(data)
                    data = TempFile(data, name=filename)
                is_last_data = chunk_num == chunks - 1
                is_last_sample = is_last_data and path == reads[-1]
                resp = self.execute(UPLOAD_SAMPLE, variables={
                    "blob": data, "isLastData": is_last_data,
                    "isLastSample": is_last_sample,
                    "expectedFileSize": chunk_num * chunk_size,
                    "data": data_id, "filename": filename,
                    "sampleName": name, "previousData": previous_data,
                    **(metadata or {})
                })
                data_id = resp["data"]["uploadDemultiplexedData"]["dataId"]
                sample_id = resp["data"]["uploadDemultiplexedData"]["sampleId"]
                if is_last_data:
                    previous_data.append(data_id)
                    data_id = None
        return self.sample(sample_id)


    def upload_annotation(self, path, lane_id=None, lane_name=None, ignore_warnings=False, chunk_size=1_000_000, progress=False, use_base64=True):
        """Uploads an annotation sheet to the server.

        :param str path: The path to the annotation sheet.
        :param str lane_id: The ID of the existing lane to upload to.
        :param str lane_name: The name of the new lane to upload to.
        :param bool ignore_warnings: Whether to ignore warnings.
        :param int chunk_size: The size of each chunk to upload.
        :param bool progress: Whether to show a progress bar.
        :rtype: ``dict``"""

        size = os.path.getsize(path)
        chunks = math.ceil(size / chunk_size)
        data_id = None
        if bool(lane_id) + bool(lane_name) != 1:
            raise ValueError("One of lane_id or lane_name must be specified.")
        chunk_nums = tqdm(range(chunks)) if progress else range(chunks)
        for chunk_num in chunk_nums:
            filename = Path(path).name
            if progress: chunk_nums.set_description(f"Uploading {filename}")
            with open(path, "rb") as f:
                f.seek(chunk_num * chunk_size)
                data = f.read(chunk_size)
                if use_base64: data = base64.b64encode(data)
                data = TempFile(data, name=filename)
                resp = self.execute(UPLOAD_ANNOTATION, variables={
                    "blob": data,
                    "isLast": chunk_num == chunks - 1,
                    "expectedFileSize": chunk_num * chunk_size,
                    "data": data_id,
                    "laneName": lane_name,
                    "lane": lane_id,
                    "ignoreWarnings": ignore_warnings,
                    "filename": filename
                })
                data_id = resp["data"]["uploadAnnotationData"]["dataId"]
        return self.data(data_id)


    def upload_multiplexed(self, path, lane_id=None, lane_name=None, chunk_size=1_000_000, progress=False, use_base64=True):
        """Uploads a multiplexed reads file to the server.

        :param str path: The path to the multiplexed reads file.
        :param str lane_id: The ID of the existing lane to upload to.
        :param str lane_name: The name of the new lane to upload to.
        :param int chunk_size: The size of each chunk to upload.
        :param bool progress: Whether to show a progress bar.
        :rtype: ``dict``"""
        
        size = os.path.getsize(path)
        chunks = math.ceil(size / chunk_size)
        data_id = None
        if bool(lane_id) + bool(lane_name) != 1:
            raise ValueError("One of lane_id or lane_name must be specified.")
        chunk_nums = tqdm(range(chunks)) if progress else range(chunks)
        for chunk_num in chunk_nums:
            filename = Path(path).name
            if progress: chunk_nums.set_description(f"Uploading {filename}")
            with open(path, "rb") as f:
                f.seek(chunk_num * chunk_size)
                data = f.read(chunk_size)
                if use_base64: data = base64.b64encode(data)
                data = TempFile(data, name=filename)
                resp = self.execute(UPLOAD_MULTIPLEXED, variables={
                    "blob": data,
                    "isLast": chunk_num == chunks - 1,
                    "expectedFileSize": chunk_num * chunk_size,
                    "data": data_id,
                    "laneName": lane_name,
                    "lane": lane_id,
                    "filename": filename
                })
                data_id = resp["data"]["uploadMultiplexedData"]["dataId"]
        return self.data(data_id)


    def upload_lane(self, name, annotation_path, multiplexed_path, ignore_warnings=False, chunk_size=1_000_000, progress=False, use_base64=True):
        """Uploads an annotation sheet and multiplexed reads file to the server.

        :param str name: The name of the new lane.
        :param str annotation_path: The path to the annotation sheet.
        :param str multiplexed_path: The path to the multiplexed reads file.
        :param bool ignore_warnings: Whether to ignore warnings in annotation.
        :param int chunk_size: The size of each chunk to upload.
        :param bool progress: Whether to show a progress bar.
        :rtype: ``dict``"""

        annotation = self.upload_annotation(
            annotation_path, lane_name=name,
            ignore_warnings=ignore_warnings,
            chunk_size=chunk_size, progress=progress,
            use_base64=use_base64
        )
        lane_id = annotation["annotationLane"]["id"]
        self.upload_multiplexed(
            multiplexed_path, lane_id=lane_id,
            chunk_size=chunk_size, progress=progress,
            use_base64=use_base64
        )
        return self.lane(lane_id)