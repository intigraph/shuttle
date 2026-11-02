# Advance a local run through signed steps

This 24-second recording uses the real Shuttle 0.6.1 CLI with a public two-step workflow. It defines and starts a run, signs the review and publish transitions, then reports the terminal state. The timestamps are fixed fixture times, not a deployment timeline. Native output is preserved.

All state and newly generated demo keys stay under the recorder’s private HOME. No key is registered, no event is exported, and no Quipu call, signing enrollment, work-item reconciliation or production workflow is performed. Local signatures do not prove remote identity admission. The public fixture is `terminal/fixture/workflow.json`; private keys are never recording inputs or published artifacts.

With a verified Shuttle 0.6.1 installation, prepare a new, absent workspace:

```sh
mkdir /tmp/shuttle-demo
cp docs/demos/terminal/fixture/workflow.json /tmp/shuttle-demo/
touch /tmp/shuttle-demo/.terminal-demo-sandbox
python3 docs/demos/terminal/render.py docs/demos/terminal/demo.tape.json \
  --workspace /tmp/shuttle-demo --tool shuttle="$(command -v shuttle)" \
  --output /tmp/shuttle-render
```

Do not reuse a workspace that already has the run. The manifest records the executable, fixture and output hashes; new local key material may differ on another run. Independent local controls verified both recorded signatures and rejected both tampered-state variants, without exporting anything. Read `terminal/transcript.txt` for a static alternative.

The recorder is unchanged from Tambo’s canonical `stack-terminal-24` harness at `b0765b5d8f16a6a26acb3595552f17826d965b44`, SHA-256 `bebbe000565314f18a58731f2a1a4690577db127b3673fa10a45ce74eef0f23c`. Reading holds are deliberate; actual command durations are in the manifest.
