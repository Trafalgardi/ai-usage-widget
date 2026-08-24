import os
import tomllib
import unittest

from version import __version__


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class VersionConsistencyTests(unittest.TestCase):
    def test_python_project_and_windows_metadata_match(self):
        with open(os.path.join(ROOT, "pyproject.toml"), "rb") as stream:
            project = tomllib.load(stream)
        with open(os.path.join(ROOT, "packaging", "windows-version.txt"), encoding="utf-8") as stream:
            windows_metadata = stream.read()
        self.assertEqual(__version__, project["project"]["version"])
        self.assertIn(f"StringStruct('ProductVersion', '{__version__}')", windows_metadata)
        self.assertIn(f"StringStruct('FileVersion', '{__version__}')", windows_metadata)


if __name__ == "__main__":
    unittest.main()
