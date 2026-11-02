---
name: shuttle
description: Orient agents to signed workflows and local run state.
---

<!-- BEGIN shuttle prime -->
# Shuttle agent primer

## What shuttle is

Shuttle carries workflow runs through explicit steps with signed transitions.
Its local append-only log is an outbox; Quipu is the governed shared record.
State is folded from events, rather than overwritten in place.
Signatures prove possession of a key, rather than attribution to an agent.

## Agent workflow

1. Query Quipu for the workflow, prior decisions and the intended run before acting.
2. Run `shuttle prime` for local workflow counts and signing-file metadata.
3. Review a definition, then use `define` and `start` to create an explicit run.
4. Use `--require-existing-keys` for operations that must never generate keys.
5. Advance only legal steps, export the outbox and verify exported signatures.
6. Freeze a completed window only through the reviewed operational path.

## Core commands

| Command | Use |
| --- | --- |
| `shuttle prime [--brief] [--json]` | Read local orientation without creating state |
| `shuttle prime --static` | Print the embedded primer without inspecting state |
| `shuttle prime --section 'Core commands'` | Select a heading by case-insensitive prefix |
| `shuttle define workflow.json` | Validate and append a workflow definition |
| `shuttle start NAME RUN --agent AGENT` | Start a defined workflow run |
| `shuttle --require-existing-keys advance RUN --step STEP --agent AGENT` | Sign a legal transition using an existing key |
| `shuttle status [RUN]` | Fold the local run log |
| `shuttle export` | Write the outbox to Quipu windows; report quarantine |
| `shuttle verify RUN` | Verify exported transitions using registered public keys |
| `shuttle reconcile [RUN] --agent AGENT` | Create seed steps and advance closed ones |
| `shuttle version` | Show the installed version |

## MCP tools

None. Shuttle exposes a CLI; its Quipu client is not an MCP server.

## Read scope

Prime reads bounded local `runs.jsonl` and `export-watermark.json` files from
`SHUTTLE_STATE_DIR`, defaulting to `~/.local/state/shuttle`. It folds definitions
and runs using the existing state-machine rules. Counts describe this local
outbox, not all shared workflows. The unexported tail does not account for
historical quarantine, prove successful delivery or measure Quipu freshness.
Malformed, oversized or missing data stays explicit; unknown counts are null.

Signing status inspects names and metadata under `SHUTTLE_KEY_DIR`, defaulting
to `~/.config/shuttle/keys`. It never reads private-key bytes, generates a key,
registers a public key, takes a lock or contacts Quipu. Owned regular 0600 files
are metadata candidates only: their cryptographic validity and registration
remain unmeasured. `--agent AGENT` selects one safe filename; otherwise at most
128 key entries are inspected. The entire live read has a 650 ms deadline.
Use `--state-dir PATH` and `--key-dir PATH` to inspect explicit local locations.

A missing store needs a reviewed definition and run; prime will not bootstrap
it. Key creation and human registration are separate, deliberate operations.
Use `shuttle keys --help` to inspect that interface before changing custody.

## Next steps

- [README](https://github.com/scbrown/shuttle#readme)
- [Operating guide](https://github.com/scbrown/shuttle/blob/main/docs/operating.md)
- [Shuttle skill](https://github.com/scbrown/shuttle/blob/main/skills/shuttle/SKILL.md)
- CLI reference: `shuttle --help`, `shuttle prime --help` and `shuttle keys --help`.
<!-- END shuttle prime -->
