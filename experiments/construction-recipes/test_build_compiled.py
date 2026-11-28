"""Tamper and independent exported-mesh oracle controls."""
import json
import math
from pathlib import Path
import shutil
import struct
import tempfile
import unittest
import zlib

import build_compiled as build


class ReplayTests(unittest.TestCase):
    def test_exact_source_bindings_and_regenerated_fixtures(self):
        self.assertEqual(len(build.verify_lock()["parts"]), 9)
        self.assertEqual(len(build.verify_fixtures()), 3)

    def copied_package(self, directory):
        root = Path(directory) / "package"
        shutil.copytree(build.ROOT, root, ignore=shutil.ignore_patterns("__pycache__"))
        return root

    def test_compiled_program_tamper_fails_before_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copied_package(directory)
            path = next(root.glob("compiled/*/*/source-first.scad"))
            path.write_bytes(path.read_bytes() + b"\n// changed\n")
            with self.assertRaisesRegex(ValueError, "locked file hash mismatch"):
                build.verify_lock(root)

    def test_graph_binding_survives_outer_lock_rehash(self):
        with tempfile.TemporaryDirectory() as directory:
            root = self.copied_package(directory)
            path = next(root.glob("compiled/*/*/source.graph.json"))
            data = json.loads(path.read_text())
            data["name"] += " changed"
            path.write_text(json.dumps(data))
            lock_path = root / "compiled-lock.json"
            lock = json.loads(lock_path.read_text())
            lock["files"][str(path.relative_to(root))] = build.digest(path)
            lock_path.write_text(json.dumps(lock))
            with self.assertRaisesRegex(ValueError, "compiler source binding mismatch"):
                build.verify_lock(root)

    @staticmethod
    def tetrahedron():
        a, b, c, d = (0.0, 0.0, 0.0), (0.001, 0.0, 0.0), (0.0, 0.001, 0.0), (0.0, 0.0, 0.001)
        return [(a, c, b), (a, b, d), (a, d, c), (b, c, d)]

    def test_oriented_closed_export_control(self):
        receipt = build.audit_triangles(self.tetrahedron())
        self.assertEqual(receipt["edge_closure"], "PASS")
        self.assertAlmostEqual(receipt["signed_volume_m3"], 1e-9 / 6)

    def test_open_misoriented_overused_and_collapsed_controls(self):
        good = self.tetrahedron()
        bad_cases = [good[:-1], [tuple(reversed(good[0])), *good[1:]], [*good, good[0]],
                     [((0, 0, 0), (1e-10, 0, 0), (2e-10, 0, 0))]]
        for triangles in bad_cases:
            with self.subTest(triangles=triangles):
                with self.assertRaises(ValueError):
                    build.audit_triangles(triangles)

    def test_coarse_grid_fragility_is_separate_from_export_identity(self):
        tiny = [[tuple(value * 1e-7 for value in vertex) for vertex in triangle]
                for triangle in self.tetrahedron()]
        report = build.audit_triangles(tiny)
        self.assertEqual(report["edge_closure"], "PASS")
        self.assertEqual(report["faces_collapsed_by_fragility_grid"], 4)
        self.assertGreater(report["signed_volume_m3"], 0)

    def test_nonfinite_control(self):
        for value in (math.nan, math.inf, -math.inf):
            with self.subTest(value=value):
                with self.assertRaisesRegex(ValueError, "nonfinite"):
                    build.audit_triangles([((value, 0, 0), (0, 1, 0), (0, 0, 1))])

    def parser_fixture(self, directory, wrong_id=False):
        # Minimal parser controls, not claimed as actual Blender/render evidence.
        root = Path(directory)
        scene_path = build.ROOT / "fixtures/brick_bridge/spec.json"
        scene = json.loads(scene_path.read_text())
        nodes = [{"name": part["id"], "mesh": i, "extras": {
            "oneirifact_instance_id": part["id"], "oneirifact_definition_id": part["definition_id"],
            "oneirifact_definition_hash": part["definition_hash"], "oneirifact_source_scene_sha256": build.digest(scene_path)}}
            for i, part in enumerate(scene["instances"])]
        if wrong_id:
            nodes[0]["name"] = "unexpected_part"
        document = json.dumps({"nodes": nodes}).encode()
        document += b" " * (-len(document) % 4)
        (root / "assembly.glb").write_bytes(struct.pack("<4sII", b"glTF", 2, 20 + len(document))
            + struct.pack("<I4s", len(document), b"JSON") + document)
        header = b"IHDR" + struct.pack(">IIBBBBB", 1000, 800, 8, 6, 0, 0, 0)
        png = b"\x89PNG\r\n\x1a\n" + struct.pack(">I", 13) + header + struct.pack(">I", zlib.crc32(header) & 0xffffffff)
        for name in ("assembled.png", "exploded.png"):
            (root / name).write_bytes(png)
        (root / "assembly.blend").write_bytes(b"parser-only fixture")
        receipt = {"blender": "PARSER_FIXTURE", "files": {p.name: build.digest(p) for p in root.iterdir()}}
        (root / "render-receipt.json").write_text(json.dumps(receipt))
        return scene_path

    def test_readback_detects_glb_identity_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            scene = self.parser_fixture(directory, wrong_id=True)
            with self.assertRaisesRegex(ValueError, "instance identity mismatch"):
                build.verify_render(scene, Path(directory))

    def test_readback_checks_artifact_digests(self):
        with tempfile.TemporaryDirectory() as directory:
            scene = self.parser_fixture(directory)
            root = Path(directory)
            self.assertEqual(build.verify_render(scene, root)["named_glb_nodes"], 10)
            (root / "exploded.png").write_bytes((root / "exploded.png").read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                build.verify_render(scene, root)


if __name__ == "__main__":
    unittest.main()
