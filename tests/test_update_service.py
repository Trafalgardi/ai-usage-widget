import json
import unittest
import urllib.error

import update_service


class _Response:
    def __init__(self, payload):
        self.payload = payload
    def __enter__(self):
        return self
    def __exit__(self, *args):
        return False
    def read(self):
        return self.payload


class UpdateServiceTests(unittest.TestCase):
    def test_newer_release_is_reported_without_downloading(self):
        def opener(_request, timeout):
            self.assertEqual(3, timeout)
            return _Response(json.dumps({"tag_name": "v9.0.0", "html_url": "https://example.test/release"}).encode())
        result = update_service.check_for_updates(timeout=3, opener=opener)
        self.assertTrue(result["success"])
        self.assertEqual("update_available", result["status"])

    def test_malformed_response_is_safe(self):
        result = update_service.check_for_updates(opener=lambda *_args, **_kwargs: _Response(b"not-json"))
        self.assertFalse(result["success"])
        self.assertEqual("malformed_release", result["status"])

    def test_timeout_is_network_error(self):
        def opener(*_args, **_kwargs):
            raise urllib.error.URLError("timed out")
        result = update_service.check_for_updates(opener=opener)
        self.assertEqual("network_error", result["status"])


if __name__ == "__main__":
    unittest.main()
