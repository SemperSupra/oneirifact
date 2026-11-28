"""Checks for the static project showcase, not for the procedural engine."""
from html.parser import HTMLParser
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "site"


class SiteParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.tags = []
        self.attrs = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)
        self.attrs.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


class PublicSiteTests(unittest.TestCase):
    def setUp(self):
        self.parser = SiteParser()
        self.parser.feed((SITE / "index.html").read_text(encoding="utf-8"))

    def test_static_showcase_only(self):
        self.assertIn(sorted(p.name for p in SITE.iterdir()), [["anatomy", "index.html"], ["anatomy", "gallery", "index.html"], ["anatomy", "gallery", "index.html", "inspect"]])
        self.assertTrue((SITE / "index.html").is_file())
        self.assertFalse((SITE / "index.html").is_symlink())
        self.assertIn("Browser preview in preparation", self.parser.text)
        self.assertIn("The interactive editor is not yet available.", " ".join(self.parser.text))

    def test_explicit_renderer_source_boundary(self):
        text = " ".join(self.parser.text)
        self.assertIn("standalone Python/Blender procedural recipe", text)
        self.assertIn("not native Oneirifact feature graphs", text)
        self.assertIn("No native Oneirifact pavilion artifact", text)
        self.assertIn("Native Oneirifact artifact gallery — not yet published", text)

    def test_semantic_document(self):
        self.assertEqual(self.parser.tags.count("h1"), 1)
        self.assertEqual(self.parser.tags.count("main"), 1)
        self.assertIn(("html", {"lang": "en"}), self.parser.attrs)
        ids = {a["id"] for _, a in self.parser.attrs if "id" in a}
        for _, attrs in self.parser.attrs:
            if "aria-labelledby" in attrs:
                self.assertIn(attrs["aria-labelledby"], ids)

    def test_gallery_generated_files(self):
        if not (SITE / "gallery").exists():
            self.skipTest("Build gallery with pinned Blender to qualify actual assets")
        expected = {f"{p}{ext}" for p in ("pavilion-day","pavilion-night","pavilion-plan","pavilion-tall","bearing-assembled","bearing-exploded") for ext in (".png",".blend",".glb",".json")} | {"pavilion.py","specs.json","export_gallery.py","bearing.py"}
        self.assertEqual({p.name for p in (SITE/"gallery").iterdir()}, expected)
        for p in (SITE/"gallery").iterdir():
            self.assertTrue(p.is_file() and not p.is_symlink() and p.stat().st_size > 0)

    def test_no_active_external_content(self):
        self.assertFalse(set(self.parser.tags) & {"script", "iframe", "object", "embed", "form", "link"})
        profiles = ('pavilion-day', 'pavilion-night', 'pavilion-plan', 'pavilion-tall', 'bearing-assembled', 'bearing-exploded')
        expected_images = {f'gallery/{p}.png' for p in profiles}
        links = set()
        for tag, attrs in self.parser.attrs:
            self.assertFalse(any(k.startswith("on") for k in attrs))
            if "src" in attrs:
                self.assertEqual(tag, "img")
                self.assertIn(attrs["src"], expected_images)
                self.assertTrue(attrs.get("alt"))
            if "href" in attrs:
                self.assertEqual(tag, "a")
                links.add(attrs["href"])
        self.assertEqual(links, {
            "https://github.com/SemperSupra/oneirifact",
            "https://github.com/SemperSupra/oneirifact/issues",
            "anatomy/",
        } | {f"gallery/{p}{ext}" for p in profiles for ext in (".png",".blend",".glb",".json")} | {f"inspect/{p}.html" for p in profiles} | {"inspect/index.html","inspect/specs.json.html","inspect/pavilion.py.html","inspect/export_gallery.py.html","inspect/bearing.py.html"})


if __name__ == "__main__":
    unittest.main()
