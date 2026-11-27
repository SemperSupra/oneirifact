"""Commit-exact scanner staging negatives; no credentials or scanner required."""
import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from scan_public_source import stage_tracked, scan_inventory, run_scan


class ScanStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.git("init", "-q")
        self.git("config", "user.email", "fixture@example.invalid")
        self.git("config", "user.name", "Fixture")
        (self.repo / "sample.txt").write_bytes(b"committed")
        self.git("add", ".")
        self.git("commit", "-qm", "fixture")
        self.head = self.git("rev-parse", "HEAD").strip()
        self.stage = self.root / "stage"
        self.stage.mkdir()

    def git(self, *args):
        return subprocess.check_output(["git", "-C", str(self.repo), *args], text=True)

    def test_mutable_worktree_does_not_control_scan(self):
        (self.repo / "sample.txt").write_bytes(b"tampered!")
        (self.repo / "other.txt").write_bytes(b"not in commit")
        self.git("add", ".")
        manifest = stage_tracked(self.stage, self.repo, self.head)
        self.assertEqual(manifest, {"sample.txt": hashlib.sha256(b"committed").hexdigest()})
        self.assertEqual((self.stage / "sample.txt").read_bytes(), b"committed")
        self.assertFalse((self.stage / "other.txt").exists())

    def test_missing_empty_and_symlink_targets_rejected(self):
        for p in (self.root / "absent", self.stage):
            with self.assertRaises(RuntimeError):
                scan_inventory(p)
        (self.stage / "alias").symlink_to(self.repo / "sample.txt")
        with self.assertRaises(RuntimeError):
            scan_inventory(self.stage)

    def test_symlink_commit_rejected(self):
        (self.repo / "alias").symlink_to("sample.txt")
        self.git("add", ".")
        self.git("commit", "-qm", "link")
        with self.assertRaises(RuntimeError):
            stage_tracked(self.stage, self.repo)

    def test_case_conflicting_paths_rejected(self):
        (self.repo / "A").mkdir()
        (self.repo / "a").mkdir()
        (self.repo / "A" / "first.txt").write_text("a")
        (self.repo / "a" / "second.txt").write_text("b")
        self.git("add", ".")
        self.git("commit", "-qm", "case")
        with self.assertRaises(RuntimeError):
            stage_tracked(self.stage, self.repo)

    def test_manifest_mismatch_prevents_scanner_invocation(self):
        manifest = stage_tracked(self.stage, self.repo, self.head)
        (self.stage / "sample.txt").write_bytes(b"tampered!")
        with patch("scan_public_source.subprocess.run") as invoke:
            with self.assertRaises(RuntimeError):
                run_scan(Path("/nonexistent"), self.root, "test", self.stage,
                         expected_manifest=manifest)
            invoke.assert_not_called()

    def test_stage_change_during_scan_rejected(self):
        manifest = stage_tracked(self.stage, self.repo, self.head)
        def mutate(*args, **kwargs):
            (self.stage / "sample.txt").write_bytes(b"tampered!")
            return subprocess.CompletedProcess(args, 0, "", "")
        with patch("scan_public_source.subprocess.run", side_effect=mutate):
            with self.assertRaises(RuntimeError):
                run_scan(Path("/nonexistent"), self.root, "test", self.stage,
                         expected_manifest=manifest)


if __name__ == "__main__":
    unittest.main()
