import shutil
import socket
import subprocess
from pathlib import Path
from unittest import TestCase

class ServerTestCase(TestCase):
    
    @classmethod
    def setUpClass(cls):
        cls.sever_location = Path("tests", "test-server")
        cls.tearDownClass()
        cls.sever_location.mkdir(exist_ok=True)
        subprocess.run([
            "git", "clone", "https://github.com/goodwright/flow-api.git",
            str(cls.sever_location)
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(
            ["git", "checkout", "1.0"], cwd=cls.sever_location, check=True,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["pip", "install", "-r", "requirements.txt"],
            cwd=cls.sever_location, check=True, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        subprocess.run(
            ["python", "manage.py", "migrate"],
            cwd=cls.sever_location, check=True, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        Path("tests", "uploads").mkdir(exist_ok=True)
    

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.sever_location, ignore_errors=True)
        shutil.rmtree(Path("tests", "uploads"), ignore_errors=True)
    

    def setUp(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("", 0))
            self.port = str(s.getsockname()[1])
        self.process = subprocess.Popen(
            ["python", "manage.py", "runserver", self.port],
            cwd=self.sever_location, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        self.live_server_url = f"http://localhost:{self.port}/graphql"


    def tearDown(self):
        self.process.terminate()
        self.process.wait()