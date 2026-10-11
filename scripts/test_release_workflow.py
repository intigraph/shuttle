# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml==6.0.2"]
# ///
"""Exercise publication boundaries with a private fake transport."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parent.parent


class ReleaseWorkflowTests(unittest.TestCase):
    def test_release_pr_calls_publisher_only_after_tag_creation(self):
        producer = yaml.load(
            (ROOT / ".github/workflows/release-pr.yml").read_text(),
            Loader=yaml.BaseLoader,
        )
        publisher = yaml.load(
            (ROOT / ".github/workflows/release.yml").read_text(),
            Loader=yaml.BaseLoader,
        )
        self.assertIn("main", producer["on"]["push"]["branches"])
        call = producer["jobs"]["publish"]
        self.assertEqual(call["if"], "needs.release-please.outputs.release_created == 'true'")
        self.assertEqual(call["uses"], "./.github/workflows/release.yml")
        self.assertEqual(publisher["on"]["workflow_call"]["inputs"]["tag"]["required"], "true")
        self.assertEqual(
            publisher["jobs"]["release"]["steps"][0]["with"]["ref"],
            "${{ inputs.tag || github.ref_name }}",
        )

    def test_authentication_split_and_missing_secret(self):
        producer = yaml.load((ROOT / ".github/workflows/release-pr.yml").read_text(), Loader=yaml.BaseLoader)
        steps = producer["jobs"]["release-please"]["steps"]
        guard, release, release_pr = steps
        self.assertEqual(guard["env"]["RELEASE_PLZ_TOKEN"], "${{ secrets.RELEASE_PLZ_TOKEN }}")
        self.assertEqual(release["with"]["token"], "${{ github.token }}")
        self.assertEqual(release["with"]["skip-github-pull-request"], "true")
        self.assertEqual(release_pr["with"]["token"], "${{ secrets.RELEASE_PLZ_TOKEN }}")
        self.assertEqual(release_pr["with"]["skip-github-release"], "true")
        for value, ok in [(None, False), ("", False), ("fixture-credential", True)]:
            with self.subTest(secret=value is not None):
                env = {"PATH": "/usr/bin:/bin"}
                if value is not None:
                    env["RELEASE_PLZ_TOKEN"] = value
                result = subprocess.run(["/bin/bash", "-c", guard["run"]], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, ok)
                self.assertNotIn("fixture-credential", result.stdout + result.stderr)

    def test_release_pr_updates_the_declared_version_files(self):
        config = json.loads((ROOT / "release-please-config.json").read_text())
        manifest = json.loads((ROOT / ".release-please-manifest.json").read_text())
        self.assertEqual(config["release-type"], "simple")
        self.assertTrue(config["draft"])
        self.assertTrue(config["force-tag-creation"])
        self.assertIn({"type": "generic", "path": "shuttle/__init__.py"}, config["packages"]["."]["extra-files"])
        version = (ROOT / "version.txt").read_text().strip()
        self.assertEqual(manifest["."], version)
        target = (ROOT / "shuttle/__init__.py").read_text()
        self.assertIn("x-release-please-version", target)
        self.assertIn(version, target)

    def test_draft_publication_and_failures(self):
        workflow = yaml.load(
            (ROOT / ".github/workflows/release.yml").read_text(),
            Loader=yaml.BaseLoader,
        )
        body = next(
            step["run"]
            for step in workflow["jobs"]["release"]["steps"]
            if step.get("name") == "Publish the release"
        )
        stub = r"""#!/usr/bin/python3
import json, os, sys
with open(os.environ["CALL_LOG"], "a") as output:
    output.write(json.dumps(sys.argv[1:]) + "\n")
command = sys.argv[2]
if command == "view":
    print("false" if os.environ["CONTROL"] == "published" else "true")
    if os.environ["CONTROL"] == "view-failed":
        sys.exit(1)
if command == "upload" and os.environ["CONTROL"] == "upload-failed":
    sys.exit(1)
"""
        cases = [
            ("draft", ["view", "upload", "edit"], True),
            ("published", ["view"], False),
            ("view-failed", ["view"], False),
            ("upload-failed", ["view", "upload"], False),
            ("tag", ["create"], True),
        ]
        for control, expected, succeeds in cases:
            with self.subTest(control=control), tempfile.TemporaryDirectory() as scratch:
                root = Path(scratch)
                (root / "bin").mkdir()
                transport = root / "bin" / "gh"
                transport.write_text(stub)
                transport.chmod(0o700)
                (root / "dist").mkdir()
                (root / "dist" / "shuttle-v0.3.1.whl").write_text("fixture")
                (root / "dist" / "checksums.txt").write_text("fixture")
                shell = root / "publish.sh"
                shell.write_text(body)
                env = {
                    "HOME": scratch,
                    "PATH": f"{root / 'bin'}:/usr/bin:/bin",
                    "CONTROL": control,
                    "CALL_LOG": str(root / "calls"),
                    "RELEASE_TAG": "v0.3.1",
                    "RELEASE_FROM_PR": "" if control == "tag" else "v0.3.1",
                    "GITHUB_REPOSITORY": "example/shuttle",
                    "RUNNER_TEMP": scratch,
                }
                result = subprocess.run(
                    ["/bin/bash", str(shell)],
                    cwd=root,
                    env=env,
                    capture_output=True,
                    text=True,
                    check=False,
                )
                calls = [json.loads(line) for line in (root / "calls").read_text().splitlines()]
                self.assertEqual([call[1] for call in calls], expected)
                self.assertEqual(result.returncode == 0, succeeds)
                self.assertTrue(all("--clobber" not in call for call in calls))


if __name__ == "__main__":
    unittest.main()
