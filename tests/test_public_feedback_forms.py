"""Offline acceptance for original public-only issue intake templates.

This does not imply that feedback has been received, nor validate user-supplied
content or prove any interactive Oneirifact capability exists.
"""
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
TEMPLATES = ROOT / ".github" / "ISSUE_TEMPLATE"
FORMS = {
    "bug-report.yml": {"surface", "reproduce", "expected", "actual", "privacy"},
    "usability-accessibility.yml": {"surface", "interaction", "task", "barrier", "privacy"},
    "feature-request.yml": {"audience", "goal", "proposed", "privacy"},
}


class PublicFeedbackTemplates(unittest.TestCase):
    def test_only_reviewed_original_template_paths(self):
        self.assertEqual(
            {p.name for p in TEMPLATES.iterdir()},
            set(FORMS) | {"config.yml"},
        )
        for item in TEMPLATES.iterdir():
            self.assertTrue(item.is_file())
            self.assertFalse(item.is_symlink())
        self.assertEqual(
            (TEMPLATES / "config.yml").read_text(encoding="utf-8"),
            "blank_issues_enabled: true\n",
        )

    def test_each_form_has_complete_github_issue_schema(self):
        for filename, required in FORMS.items():
            with self.subTest(filename=filename):
                text = (TEMPLATES / filename).read_text(encoding="utf-8")
                for heading in ("name: ", "description: ", "title: ", "body:"):
                    self.assertIn(heading, text)
                self.assertIn("  - type: markdown\n", text)
                self.assertIn("  - type: checkboxes\n", text)
                ids = re.findall(r"^    id: ([a-z][a-z0-9_-]*)$", text, re.MULTILINE)
                self.assertEqual(len(ids), len(set(ids)))
                self.assertTrue(required <= set(ids))
                self.assertIn("      label: Public-information check\n", text)
                self.assertIn("          required: true\n", text)

    def test_reporting_does_not_require_private_data_or_telemetry(self):
        forbidden = ("action:", "upload:", "webhook:", "<script", "http://",
                     "https://", "api_key:", "secret:", "token:", "image:")
        for filename in FORMS:
            with self.subTest(filename=filename):
                text = (TEMPLATES / filename).read_text(encoding="utf-8")
                self.assertFalse(any(k in text for k in forbidden))
                self.assertTrue(any(k in text.lower() for k in ("private", "confidential")))
                self.assertIn("credentials", text.lower())

    def test_current_public_capability_is_not_misrepresented(self):
        bug = (TEMPLATES / "bug-report.yml").read_text(encoding="utf-8")
        ux = (TEMPLATES / "usability-accessibility.yml").read_text(encoding="utf-8")
        feature = (TEMPLATES / "feature-request.yml").read_text(encoding="utf-8")
        self.assertIn("not yet the procedural editor", bug)
        self.assertIn("when released", ux)
        self.assertIn("unannounced capability", feature)


if __name__ == "__main__":
    unittest.main()
