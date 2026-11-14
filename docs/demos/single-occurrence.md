# Single-occurrence cadence demo

Base `0b6b8492497c6f9e83027efb624f7e3a6dc13188` refuses this configuration.
The candidate accepts only UTC slot600 and refuses slots599,601,660 and86400.
Candidate scheduled_cli SHA256: `ba816598363effb4346dc35b0545cd16f22d337d5647590b6ea7cbb3f16a7011`.

[Recording](single-occurrence.log), [timing](single-occurrence.timing).
Download both and replay with `scriptreplay --log-out single-occurrence.log --log-timing single-occurrence.timing`.
The log also provides a readable transcript; no inline playback is claimed.

```sh
git show 0b6b8492497c6f9e83027efb624f7e3a6dc13188:shuttle/scheduled_cli.py > /tmp/scheduled-cli-base.py
python scripts/demo-single-occurrence.py --before /tmp/scheduled-cli-base.py
```

Pure cadence predicate; the before module uses current sibling import helpers.
No graph, key, signatures, child process, enrollment or runtime admission is
exercised. Small sanitized recording is retained with the existing demos.
