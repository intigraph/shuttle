<p align="center"><img src="assets/thread-workshop/shuttle.png" width="704" alt="shuttle: A wooden shuttle crosses ordered warp threads. Original pixel art in the Thread Workshop style."/></p>

<p align="center">
  <img src="assets/logo.svg" width="220" alt="Shuttle logo — a weaving shuttle carrying a red weft thread through vertical warp threads, with a small knot seal below"/>
</p>

# Shuttle

Signed agent workflows with append-only execution records. Steps link back
to work items and export their evidence to Quipu.

## Why you would want it

- **Keep workflow evidence:** append a signed record for each transition.
- **Check legal steps:** advance runs according to their declared state machine.
- **Share completed history:** export evidence to governed Quipu graphs.

## Install

```sh
curl -fsSL https://raw.githubusercontent.com/scbrown/shuttle/main/install.sh | sh
```

Python 3.11+ with venv/pip, curl, and a Linux or macOS shell. Downloads the latest checksummed wheel into its own virtual environment;
command links go in `~/.local/bin`. Add that directory to `PATH`.

Set `STACK_INSTALL_ROOT` on the receiving shell for another prefix.
Pinned releases, alternatives, configuration and removal are in the
[installation and usage reference](docs/installation-reference.md).

## First success in three commands

![Animated terminal: Define a local workflow, advance through signed steps, and inspect its terminal state](docs/demos/terminal/demo.svg)

The public fixture uses private local state and demo keys; nothing is registered or exported.
[Read the transcript](docs/demos/terminal/transcript.txt) or
[reproduce the recording](docs/demos/terminal.md).

Check the installed workflow engine:

```sh
shuttle version
```

[Create a workflow](docs/installation-reference.md#quick-start) when you are ready
to register an agent identity. Installation does not enroll a key or run a workflow.

## On your own data

| You want to | Run |
|---|---|
| Define a workflow | `shuttle define examples/triage.json` |
| Inspect local run state | `shuttle status` |
| Inspect available operations | `shuttle --help` |

The [quick-start reference](docs/installation-reference.md#quick-start)
covers identity setup, starting runs, signed advances and export. The embedded
recording uses isolated local keys and state; it registers and exports nothing.

## Wire it into your agent

Configure each agent's signing identity before allowing it to advance runs.
`shuttle keys init` prepares a key and registration material; a human registers
the public key. Shuttle does not enroll itself. See the
[identity and workflow reference](docs/installation-reference.md#quick-start).
Seeds can perform configured workflow steps; reconciliation is a separate
operation that must be explicitly configured.

## Before you start

The installer needs Python 3.11+ with venv/pip, curl and Linux or macOS.
The engine uses the `cryptography` package for signatures. Keep signing keys
private and retain the append-only local state. Quipu export and signature
verification from the graph need a configured server and registered public keys.

## What's next

- [The Shuttle book](https://intigraph.github.io/shuttle/): concepts and usage.
- [Installation reference](docs/installation-reference.md): configuration and removal.
- [Reproduce the terminal demo](docs/demos/terminal.md): local fixture and full output.

### Related tools and repository knowledge

- [Tambo](https://github.com/intigraph/tambo): guided stack installation and verification.
- [Camayoc](https://github.com/scbrown/camayoc): governed memory and vocabulary.
- [Detailed examples and agent setup](docs/installation-reference.md).

**Load this repository’s graph:** public repository-pendant assets have not yet been verified. When a release supplies the archive, checksum and provenance, follow the [verified import workflow](https://scbrown.github.io/quipu/sharing/index.html): extract the share directory and use `quipu import SHARE_DIR --db repository.db`. Import stages knowledge; ROOT stays unchanged.

## 🧺 The stack

<!-- stack-table:start -->

The Quipu stack is built around a governed, bitemporal knowledge store: shared
facts, decisions and work history your agents can query. Quipu can check writes
against your rules, records where each fact came from, and answers what was true
when.

| tool | what it gives your agents |
|---|---|
| [tambo](https://github.com/intigraph/tambo) | 🧰 Agent Platform Toolkit - installs and configures the quipu stack |
| [quipu](https://github.com/scbrown/quipu) | stores shared facts with provenance and history; can check writes against your rules |
| [camayoc](https://github.com/scbrown/camayoc) | prepares knowledge and vocabulary for Quipu, with checks before it is admitted |
| [quechua](https://github.com/scbrown/quechua) | shared vocabulary and shapes for interoperable knowledge |
| [chaski](https://github.com/scbrown/chaski) | reacts to graph changes and delivers governed notifications |
| [bobbin](https://github.com/scbrown/bobbin) | indexes your codebase and injects context from that index and Quipu knowledge |
| [yupana](https://github.com/scbrown/yupana) | shows code impact and can read policies from Quipu to govern agent actions |
| [desire-path](https://github.com/scbrown/desire-path) | turns agent mistakes into feature requests; works on its own without Quipu |
| [seeds](https://github.com/scbrown/seeds) | a work item tracker backed by the Quipu knowledge base |
| [shantytown](https://github.com/scbrown/shantytown) | runs crews of AI agents on work items, triggered by hand, on a schedule or by events; can share work and memory through Quipu |
| [rikuy](https://github.com/scbrown/rikuy) | live brief: status, graphs, watches and signed decisions over Quipu |
| [shuttle](https://github.com/scbrown/shuttle) | runs signed agent workflows and keeps their records in Quipu |

<!-- stack-table:end -->


## Contributing

Run `just check` and `just test` before submitting a change.

## 📜 License

[License](LICENSE).
