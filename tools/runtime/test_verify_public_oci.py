import hashlib
import io
import json
import unittest
from unittest.mock import patch

from verify_public_oci import verify


class PublicOciTests(unittest.TestCase):
    def graph(self, corrupt=False):
        objects = {}

        def add(value):
            data = value if isinstance(value, bytes) else json.dumps(value).encode()
            digest = "sha256:" + hashlib.sha256(data).hexdigest()
            objects[digest] = data
            return {"digest": digest, "size": len(data)}

        blob = add(b"wasm-test")
        manifest = add({"config": blob, "layers": [blob]})
        index = add({"manifests": [manifest]})
        if corrupt:
            objects[blob["digest"]] = b"corrupt"

        def open_url(request, timeout):
            if isinstance(request, str):
                self.assertTrue(request.startswith("https://ghcr.io/token?"))
                return io.BytesIO(b'{"token":"anonymous-test"}')
            return io.BytesIO(objects[request.full_url.rsplit("/", 1)[-1]])

        with patch("urllib.request.urlopen", side_effect=open_url):
            return verify("ghcr.io/trycua/inspircd", index["digest"])

    def test_complete_graph_and_deduplication(self):
        result = self.graph()
        self.assertTrue(result["anonymous_pull"])
        self.assertEqual(len(result["verified"]), 3)
        self.assertNotIn("anonymous-test", json.dumps(result))

    def test_corruption_fails(self):
        with self.assertRaisesRegex(ValueError, "digest mismatch"):
            self.graph(corrupt=True)

    def test_rejects_mutable_reference(self):
        with self.assertRaises(ValueError):
            verify("ghcr.io/trycua/inspircd", "latest")


if __name__ == "__main__":
    unittest.main()
