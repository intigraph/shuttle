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

    def test_uses_the_existing_workflow_token_route(self):
        producer = yaml.load((ROOT / ".github/workflows/release-pr.yml").read_text(), Loader=yaml.BaseLoader)
        steps = producer["jobs"]["release-please"]["steps"]
        self.assertEqual(len(steps), 1)
        self.assertEqual(steps[0]["id"], "release")
        self.assertEqual(steps[0]["with"]["token"], "${{ github.token }}")
        self.assertNotIn("RELEASE_PLZ_TOKEN", json.dumps(producer))

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


class PendantAdmissionTests(unittest.TestCase):
    def test_verification_requires_explicit_publisher_admission(self):
        workflow = yaml.load((ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader)
        verify = workflow["jobs"]["repository-pendant"]
        self.assertEqual(verify["if"], "vars.SHUTTLE_PENDANT_PUBLICATION == 'enabled'")
        self.assertEqual(verify["needs"], "release")
        self.assertEqual(verify["permissions"], {"contents": "read"})
        self.assertIn("scripts/verify-repository-share.py", verify["steps"][-1]["run"])
        self.assertEqual(verify["timeout-minutes"], "45")

    def test_actual_recorded_state_is_truthful_without_publishing(self):
        workflow = yaml.load((ROOT / ".github/workflows/release.yml").read_text(), Loader=yaml.BaseLoader)
        job = workflow["jobs"]["repository-pendant-admission"]
        self.assertEqual(job["env"]["PENDANT_PUBLICATION"], "${{ vars.SHUTTLE_PENDANT_PUBLICATION }}")
        self.assertEqual(job["needs"], "release")
        for value in ("", "disabled", "enabled", "true", "ENABLED", " enabled"):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as scratch:
                summary = Path(scratch) / "summary"
                result = subprocess.run(["/bin/bash", "-c", job["steps"][0]["run"]],
                    env={"PATH": "/usr/bin:/bin", "PENDANT_PUBLICATION": value,
                         "GITHUB_STEP_SUMMARY": str(summary)},
                    capture_output=True, text=True, timeout=5)
                self.assertEqual(result.returncode, 0, result.stderr)
                expected = "ADMITTED:" if value == "enabled" else "NOT ADMITTED:"
                self.assertTrue(result.stdout.startswith(expected), result.stdout)
                self.assertEqual(summary.read_text(), result.stdout)


if __name__ == "__main__":
    unittest.main()
