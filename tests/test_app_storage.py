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

    def test_valid_legacy_config_is_copied_once_without_deleting_source(self):
        with tempfile.TemporaryDirectory() as directory:
            legacy = os.path.join(directory, "legacy.json")
            current = os.path.join(directory, "new", "config.json")
            with open(legacy, "w", encoding="utf-8") as stream:
                json.dump({"language": "en", "window": {"width": 512}}, stream)
            store = ConfigStore(current, {"language": "ru", "window": {"width": 380, "height": 600}})
            self.assertTrue(store.migrate_from(legacy))
            self.assertTrue(os.path.exists(legacy))
            self.assertEqual(512, store.load()["window"]["width"])
            self.assertEqual(600, store.load()["window"]["height"])
            self.assertFalse(store.migrate_from(legacy))


if __name__ == "__main__":
    unittest.main()
