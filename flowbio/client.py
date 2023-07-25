import os
import io
import math
import kirjava
from tqdm import tqdm
from pathlib import Path

class TempFile(io.BytesIO):
    def __init__(self, *args, name="", **kwargs):
        self.name = name
        io.BytesIO.__init__(self, *args, **kwargs)


class Client(kirjava.Client):
    
    def login(self, username, password):
        """Acquires the relevant access token for the client."""
        
        response = self.execute("""mutation login(
            $username: String! $password: String!
        ) { login(username: $username password: $password) {
            accessToken
        } }""", variables={"username": username, "password": password})
        token = response["data"]["login"]["accessToken"]
        self.headers["Authorization"] = token
    

    def user(self, username):
        """Returns a user object."""

        response = self.execute("""query user(
            $username: String!
        ) { user(username: $username) {
            id username name
        } }""", variables={"username": username})
        return response["data"]["user"]


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
                resp = self.execute("""mutation uploadData(
                    $blob: Upload! $isLast: Boolean! $expectedFileSize: Float! $data: ID
                    $filename: String!
                ) { uploadData(
                    blob: $blob isLast: $isLast expectedFileSize: $expectedFileSize
                    data: $data
                    filename: $filename
                ) { dataId } }""", variables={
                    "blob": data,
                    "isLast": chunk_num == chunks - 1,
                    "expectedFileSize": chunk_num * chunk_size,
                    "data": data_id,
                    "filename": filename
                })
                data_id = resp["data"]["uploadData"]["dataId"]
        data = self.execute("""query data($id: ID!) { data(id: $id) {
            id filename filetype size category created isDirectory isBinary private
        } }""", variables={"id": data_id})["data"]["data"]   
        return data