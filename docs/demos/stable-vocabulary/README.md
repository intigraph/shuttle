# Stable vocabulary builder replay

Run `python3 docs/demos/stable-vocabulary/demo.py`. Identical private definition,
start, transition and registration inputs use old vocabulary on base
`0b6b8492497c6f9e83027efb624f7e3a6dc13188` and published vocabulary on the candidate
(the containing revision). The four builders with old vocabulary become zero;
the run identity and signature bytes stay unchanged. Unknown term ownership
refuses. This invokes pure builders with a stub public key; it proves no installed
or live-store behavior and performs no network, graph, key or scheduler operation.

[Output](output.log) and [timing](timing.log) are an output-only terminal recording.
Download both and replay with
`scriptreplay --log-out output.log --log-timing timing.log`.
No inline playback is claimed. These small sanitized files stay in this existing
demo tree with source history.
