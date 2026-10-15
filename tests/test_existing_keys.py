"""Existing-key admission must never manufacture a replacement identity."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from shuttle import signing


class ExistingKeyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "keys"
        self.args = ("urn:shuttle:run:fixture", "begin", "queued", "running", "2026-01-01T00:00:00Z")

    def test_missing_key_neither_creates_paths_nor_calls_generator(self):
        with mock.patch.object(signing.Ed25519PrivateKey, "generate", side_effect=AssertionError("generation")):
            with self.assertRaises(signing.SigningError):
                signing.sign_transition("fixture", *self.args, root=self.root, require_existing_key=True)
        self.assertFalse(self.root.exists())

    def test_existing_key_signs_the_same_canonical_message(self):
        signing.load_or_generate("fixture", self.root)
        before = (self.root / "fixture.pk8").read_bytes()
        sig = signing.sign_transition("fixture", *self.args, root=self.root, require_existing_key=True)
        self.assertTrue(signing.verify_transition(signing.public_key_hex("fixture", self.root), sig, *self.args, "fixture"))
        self.assertEqual(before, (self.root / "fixture.pk8").read_bytes())

    def test_context_covers_public_key_and_restores_on_failure(self):
        with self.assertRaises(signing.SigningError):
            with signing.existing_keys_only():
                with signing.existing_keys_only(False):
                    signing.public_key_hex("fixture", self.root)
        self.assertFalse(self.root.exists())
        self.assertEqual(64, len(signing.public_key_hex("fixture", self.root)))

    def test_unsafe_file_types_permissions_and_content_are_refused(self):
        signing.load_or_generate("fixture", self.root)
        path = self.root / "fixture.pk8"
        original = path.read_bytes()
        for mode in (0o644, 0o400, 0o700):
            with self.subTest(mode=mode):
                path.chmod(mode)
                with self.assertRaises(signing.SigningError):
                    signing.load_existing("fixture", self.root)
        path.chmod(0o600)
        with mock.patch.object(signing.os, "getuid", return_value=os.getuid() + 1):
            with self.assertRaises(signing.SigningError):
                signing.load_existing("fixture", self.root)
        for content in (b"malformed", b"x" * 16385, ec.generate_private_key(ec.SECP256R1()).private_bytes(
                serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption())):
            with self.subTest(content_length=len(content)):
                path.write_bytes(content)
                with self.assertRaises(signing.SigningError):
                    signing.load_existing("fixture", self.root)
        path.unlink()
        target = self.root / "target"
        target.write_bytes(original)
        target.chmod(0o600)
        path.symlink_to(target)
        with self.assertRaises(signing.SigningError):
            signing.load_existing("fixture", self.root)
        path.unlink()
        os.mkfifo(path, 0o600)
        with self.assertRaises(signing.SigningError):
            signing.load_existing("fixture", self.root)
        path.unlink()
        path.mkdir(mode=0o600)
        with self.assertRaises(signing.SigningError):
            signing.load_existing("fixture", self.root)

    def test_policy_requires_boolean(self):
        with self.assertRaises(signing.SigningError):
            with signing.existing_keys_only("false"):
                self.fail("entered")
        with self.assertRaises(signing.SigningError):
            signing.sign_transition("fixture", *self.args, root=self.root, require_existing_key=1)
