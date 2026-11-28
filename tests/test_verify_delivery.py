import json
from email.message import Message
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import verify_delivery as delivery


class DeliveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "site"
        self.root.mkdir()
        (self.root / "index.html").write_text("<!doctype html><title>Sample</title>")
        (self.root / "assets").mkdir()
        (self.root / "assets/demo.wasm").write_bytes(b"\x00asm\x01\x00\x00\x00")
        self.dest = self.root.parent / "stage"

    def staged(self):
        digest = delivery.stage(self.root, self.dest)
        responses = {delivery.BASE + p.relative_to(self.dest).as_posix(): p.read_bytes()
                     for p in self.dest.rglob("*") if p.is_file()}
        responses[delivery.BASE] = responses[delivery.BASE + "index.html"]
        return digest, responses

    def test_exact_multi_asset_delivery(self):
        digest, responses = self.staged()
        self.assertEqual(delivery.verify(digest, lambda u, _: responses[u]), 2)
        self.assertFalse((self.root / delivery.MANIFEST).exists())

    def test_stale_manifest_rejected_before_assets(self):
        digest, responses = self.staged()
        responses[delivery.BASE + delivery.MANIFEST] += b" "
        calls = []
        def read(url, _):
            calls.append(url)
            return responses[url]
        with self.assertRaisesRegex(ValueError, "manifest digest mismatch"):
            delivery.verify(digest, read)
        self.assertEqual(calls, [delivery.BASE + delivery.MANIFEST])

    def test_stale_module_or_wasm_rejected(self):
        digest, responses = self.staged()
        responses[delivery.BASE + "assets/demo.wasm"] = b"\x00asm\x00\x00\x00\x00"
        with self.assertRaisesRegex(ValueError, "asset mismatch"):
            delivery.verify(digest, lambda u, _: responses[u])

    def test_directory_index_route_mismatch(self):
        digest, responses = self.staged()
        responses[delivery.BASE] = b"stale HTML"
        with self.assertRaisesRegex(ValueError, "asset mismatch"):
            delivery.verify(digest, lambda u, _: responses[u])

    def test_missing_asset_rejected(self):
        digest, responses = self.staged()
        del responses[delivery.BASE + "assets/demo.wasm"]
        with self.assertRaises(KeyError):
            delivery.verify(digest, lambda u, _: responses[u])

    def test_unsafe_manifest_paths_and_duplicates(self):
        doc = delivery.inventory(self.root)
        for name in ("../secret", "/index.html", "assets/%2e%2e", "assets\\x", ".hidden", "index.html?x", delivery.MANIFEST, "INDEX.HTML"):
            with self.subTest(name=name):
                bad = json.loads(json.dumps(doc))
                bad["files"][0]["path"] = name
                bad["files"].sort(key=lambda e: e["path"])
                with self.assertRaises(ValueError):
                    delivery.validate(bad)

    def test_symlink_and_reserved_manifest_rejected(self):
        link = self.root / "link.html"
        link.symlink_to(self.root / "index.html")
        with self.assertRaisesRegex(ValueError, "unsafe site entry"):
            delivery.stage(self.root, self.dest)
        link.unlink()
        (self.root / delivery.MANIFEST).write_text("{}")
        with self.assertRaisesRegex(ValueError, "unsafe site entry"):
            delivery.stage(self.root, self.dest)

    def test_size_limits_and_destination(self):
        with patch.object(delivery, "MAX_FILE", 4):
            with self.assertRaisesRegex(ValueError, "site exceeds limits"):
                delivery.stage(self.root, self.dest)
        with self.assertRaisesRegex(ValueError, "stage inside source"):
            delivery.stage(self.root, self.root / "inside")
        delivery.stage(self.root, self.dest)
        with self.assertRaisesRegex(ValueError, "stage must not exist"):
            delivery.stage(self.root, self.dest)

    def test_schema_rejects_invalid_metadata(self):
        doc = delivery.inventory(self.root)
        for field, value in (("bytes", True), ("bytes", -1), ("sha256", "abc"), ("bytes", delivery.MAX_FILE + 1)):
            with self.subTest(field=field, value=value):
                bad = json.loads(json.dumps(doc))
                bad["files"][0][field] = value
                with self.assertRaises(ValueError):
                    delivery.validate(bad)

    def test_unexpected_origin_and_redirect(self):
        with self.assertRaisesRegex(ValueError, "unexpected asset origin"):
            delivery.fetch("https://example.invalid/index.html", 10)
        with self.assertRaisesRegex(ValueError, "unexpected asset redirect"):
            delivery.NoRedirect().redirect_request(None, None, 302, "redirect", {}, "https://example.invalid/")


    def test_browser_response_media_types(self):
        for name, content_type in (("", "text/html; charset=utf-8"),
                                   ("index.html", "text/html"),
                                   ("assets/main.mjs", "text/javascript"),
                                   ("assets/worker.js", "application/javascript; charset=UTF-8"),
                                   ("assets/core.wasm", "application/wasm"),
                                   ("assets/style.css", "text/css"),
                                   ("motion/preview.mp4", "video/mp4"),
                                   ("motion/favicon.svg", "image/svg+xml"),
                                   (delivery.MANIFEST, "application/json")):
            with self.subTest(name=name):
                headers = Message()
                headers["Content-Type"] = content_type
                delivery.verify_response_headers(delivery.BASE + name, headers)

    def test_wrong_or_missing_browser_response_media_types(self):
        for name, content_type in (("assets/core.wasm", "application/octet-stream"),
                                   ("assets/main.mjs", "text/html"),
                                   ("assets/worker.js", "text/plain"),
                                   ("assets/style.css", "application/javascript"),
                                   ("motion/preview.mp4", "text/html"),
                                   ("motion/favicon.svg", "text/plain"),
                                   (delivery.MANIFEST, "text/plain"),
                                   ("index.html", None)):
            with self.subTest(name=name):
                headers = Message()
                if content_type is not None:
                    headers["Content-Type"] = content_type
                with self.assertRaisesRegex(ValueError, "asset media type"):
                    delivery.verify_response_headers(delivery.BASE + name, headers)

    def test_ambiguous_media_type_or_content_encoding_rejected(self):
        headers = Message()
        headers["Content-Type"] = "application/wasm"
        headers["Content-Type"] = "text/html"
        with self.assertRaisesRegex(ValueError, "asset media type"):
            delivery.verify_response_headers(delivery.BASE + "core.wasm", headers)
        for encoding in ("gzip", "br", "identity, gzip"):
            with self.subTest(encoding=encoding):
                headers = Message()
                headers["Content-Type"] = "application/wasm"
                headers["Content-Encoding"] = encoding
                with self.assertRaisesRegex(ValueError, "content encoding"):
                    delivery.verify_response_headers(delivery.BASE + "core.wasm", headers)
        headers.replace_header("Content-Encoding", "identity")
        delivery.verify_response_headers(delivery.BASE + "core.wasm", headers)

    def test_fetch_checks_headers_before_reading_body(self):
        from unittest.mock import MagicMock
        response = MagicMock()
        response.__enter__.return_value = response
        url = delivery.BASE + "core.wasm"
        response.status = 200
        response.geturl.return_value = url
        response.headers = Message()
        response.headers["Content-Type"] = "text/html"
        response.read.return_value = b"same bytes"
        with patch.object(delivery.urllib.request, "build_opener") as opener:
            opener.return_value.open.return_value = response
            with self.assertRaisesRegex(ValueError, "asset media type"):
                delivery.fetch(url, 10)
            response.read.assert_not_called()
            response.headers.replace_header("Content-Type", "application/wasm")
            self.assertEqual(delivery.fetch(url, 10), b"same bytes")


if __name__ == "__main__":
    unittest.main()
