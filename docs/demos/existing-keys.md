# Existing-key signing

The same synthetic missing-key request changes from `CAPABILITY ABSENT` on
base `7da74e1ab9d188020dbd942f207af7365fe6c2ad` to `REFUSED missing key`
on this proposal. Neither request creates a path. The positive control uses a
separate synthetic key through the legacy API and verifies its signature on
both versions. No real identity, service, registration or installed binary is
used.

Run `python docs/demos/existing-keys.py` from a full clone with cryptography
installed. The candidate is the checked-out signing module; the base is read
from the exact Git object above. This example exercises the library API; the
CLI and export policy also have isolated tests.

[Terminal recording](existing-keys.log), [timing](existing-keys.timing).
Download both and play with
`scriptreplay --log-out existing-keys.log --log-timing existing-keys.timing`.
The recording was replayed locally. The small recording is retained with the
proposal as the repository's demo artifact; no external hosting is required.
