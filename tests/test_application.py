import os
import tempfile
import unittest
from unittest.mock import patch

import application


class ApplicationSmokeTests(unittest.TestCase):
    def test_smoke_check_verifies_packaged_resources_without_starting_app(self):
        with tempfile.TemporaryDirectory() as root:
            os.makedirs(os.path.join(root, "icon"))
            for relative in ("ui.html", os.path.join("icon", "512.png"), os.path.join("icon", "app.ico")):
                with open(os.path.join(root, relative), "wb") as stream:
                    stream.write(b"fixture")
            with patch("application.legacy_widget.APP_DIR", root):
                resources = application.smoke_check()
        self.assertEqual(3, len(resources))

    def test_ui_smoke_snapshot_contains_no_provider_health_secrets(self):
        snapshot = application.UiSmokeApi().get_data()
        self.assertEqual(1, snapshot["contract_version"])
        self.assertEqual({}, snapshot["provider_health"]["providers"])
        self.assertNotIn("token", str(snapshot).lower().replace("token_status", ""))


if __name__ == "__main__":
    unittest.main()
