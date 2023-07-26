import shutil
import subprocess
from pathlib import Path
from unittest import TestCase

class ServerTestCase(TestCase):
    
    @classmethod
    def setUpClass(cls):
        # Delete anything left over
        cls.sever_location = Path("tests", "test-server")
        cls.tearDownClass()

        # Make location for test server
        cls.sever_location.mkdir(exist_ok=True)

        # Clone repo
        subprocess.run([
            "git", "clone", "https://github.com/goodwright/flow-api.git",
            str(cls.sever_location)
        ], check=True)
        subprocess.run(["git", "checkout", "1.0"], cwd=cls.sever_location, check=True)

        # Make locations for stuff
        Path("tests", "uploads").mkdir(exist_ok=True)
    

    @classmethod
    def tearDownClass(cls):
        # Delete test server
        shutil.rmtree(cls.sever_location, ignore_errors=True)
        shutil.rmtree(Path("tests", "uploads"), ignore_errors=True)