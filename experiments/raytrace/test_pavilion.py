"""Original public pavilion proposal input and safety checks, not native rendering."""
import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("pavilion", ROOT / "pavilion.py")
pavilion = importlib.util.module_from_spec(spec)
spec.loader.exec_module(pavilion)


class PavilionStudyTests(unittest.TestCase):
    def setUp(self):
        self.original, self.raw = pavilion.load_specs(ROOT / "specs.json")

    def changed(self, mutate):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "sample.json"
            value = copy.deepcopy(self.original)
            mutate(value)
            path.write_text(json.dumps(value, allow_nan=True), encoding="utf-8")
            with self.assertRaises(ValueError):
                pavilion.load_specs(path)

    def test_public_original_profile_matrix(self):
        p = self.original["profiles"]
        self.assertEqual(tuple(x["id"] for x in p), pavilion.PROFILE_IDS)
        self.assertEqual(p[0]["height_m"], p[1]["height_m"])
        self.assertNotEqual(p[0]["mode"], p[1]["mode"])
        self.assertNotEqual(p[0]["height_m"], p[2]["height_m"])
        self.assertEqual(p[0]["camera"], p[2]["camera"])
        self.assertNotEqual(p[0]["camera"], p[3]["camera"])

    def test_sha_binds_input_bytes(self):
        self.assertTrue(pavilion.checksum(self.raw).startswith("sha256:"))
        self.assertNotEqual(pavilion.checksum(self.raw), pavilion.checksum(self.raw + b" "))

    def test_reject_duplicate_profile_or_unknown_fields(self):
        self.changed(lambda d: d["profiles"][1].update(id=d["profiles"][0]["id"]))
        self.changed(lambda d: d["profiles"][0].update(arbitrary_python="import os"))
        self.changed(lambda d: d.update(extra="unapproved"))

    def test_reject_nonfinite_and_type_confusion(self):
        self.changed(lambda d: d["profiles"][0].update(height_m=float("nan")))
        self.changed(lambda d: d["profiles"][0].update(height_m=True))
        self.changed(lambda d: d["profiles"][0].update(samples=True))
        self.changed(lambda d: d["profiles"][0].update(samples=0))

    def test_reject_bounds_and_unsupported_controls(self):
        self.changed(lambda d: d["profiles"][0].update(height_m=900))
        self.changed(lambda d: d["profiles"][0].update(roof_radius_m=-2))
        self.changed(lambda d: d["profiles"][0].update(mode="python"))
        self.changed(lambda d: d["profiles"][0].update(camera="arbitrary_path"))

    def test_reject_unisolated_comparison(self):
        self.changed(lambda d: d["profiles"][1].update(height_m=4.2))
        self.changed(lambda d: d["profiles"][1].update(camera="overview"))
        self.changed(lambda d: d["profiles"][2].update(height_m=d["profiles"][0]["height_m"]))

    def test_reject_duplicate_json_dictionary_key(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "duplicate.json"
            path.write_bytes(self.raw.replace(b'"schema":', b'"schema":"wrong","schema":', 1))
            with self.assertRaises(ValueError):
                pavilion.load_specs(path)

    def test_fail_closed_output_path(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            (folder / "pavilion-day.png").symlink_to(folder / "nonexistent.png")
            with self.assertRaises(ValueError):
                pavilion._output_path(str(folder), "pavilion-day")

    def test_no_external_assets_or_private_imports(self):
        source = (ROOT / "pavilion.py").read_text(encoding="utf-8")
        for forbidden in ("bpy.ops.wm.open_mainfile", "bpy.ops.import_scene",
                          "http://", "https://", "subprocess.run", "eval(",
                          "exec(", "openai", "CPE_SECRET", "PRIVATE_REPO_TOKEN"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
