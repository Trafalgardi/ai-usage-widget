import json
import os
import tempfile
import unittest

from app_storage import ConfigStore


class ConfigStoreTests(unittest.TestCase):
    def test_corrupted_config_falls_back_to_detached_defaults(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "config.json")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write("{")
            defaults = {"language": "en", "window": {"width": 380, "height": 600}}
            result = ConfigStore(path, defaults).load()
            result["window"]["width"] = 1
        self.assertEqual(380, defaults["window"]["width"])

    def test_save_replaces_file_and_leaves_no_temporary_file(self):
        with tempfile.TemporaryDirectory() as root:
            path = os.path.join(root, "config.json")
            store = ConfigStore(path, {"language": "en"})
            self.assertTrue(store.save({"language": "en", "refresh_interval_sec": 90}))
            with open(path, "r", encoding="utf-8") as stream:
                self.assertEqual(90, json.load(stream)["refresh_interval_sec"])
            self.assertFalse(os.path.exists(path + ".tmp"))


if __name__ == "__main__":
    unittest.main()
