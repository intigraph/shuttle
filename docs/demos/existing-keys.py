"""Compare the same synthetic missing-key probe on the base and candidate."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile

BASE = "7da74e1ab9d188020dbd942f207af7365fe6c2ad"


def probe(module):
    args = ("fixture", "urn:example:run", "begin", "queued", "running", "2026-01-01T00:00:00Z")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory) / "keys"
        try:
            module.sign_transition(*args, root=root, require_existing_key=True)
            result = "UNEXPECTED signed"
        except TypeError:
            result = "CAPABILITY ABSENT"
        except module.SigningError:
            result = "REFUSED missing key"
        absent = not root.exists()
        signature = module.sign_transition(*args, root=root)
        control = module.verify_transition(module.public_key_hex("fixture", root), signature, *args[1:], args[0])
        return dict(strict_missing=result, no_path_created=absent, legacy_fixture_positive_control=control)


with tempfile.TemporaryDirectory() as directory:
    base_file = Path(directory) / "base.py"
    base_file.write_bytes(subprocess.check_output(["git", "show", f"{BASE}:shuttle/signing.py"]))
    for label, path in ((f"base {BASE}", base_file), ("candidate working source", Path("shuttle/signing.py"))):
        spec = importlib.util.spec_from_file_location("demo_signing", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        print(label, flush=True)
        print(json.dumps(probe(module), sort_keys=True), flush=True)
