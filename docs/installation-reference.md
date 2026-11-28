# Installation reference

The [README](https://github.com/intigraph/shuttle#install) has the one-line
install. This page covers pinned releases, the other install routes and
removal.

## What you need

- Linux or macOS, with Python 3.11 or newer.
- For the shell installer: Python's `venv` and `pip`, and `curl`.
- A Quipu server, only for `export`, `verify` and `freeze-window`.

Shuttle has one runtime dependency, the `cryptography` package. Every route
below installs it.

## Shell installer

```sh
curl -fsSL https://raw.githubusercontent.com/intigraph/shuttle/main/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
shuttle version
```

The installer downloads the release wheel and `checksums.txt`, checks the wheel
against the checksum and installs it into its own virtual environment. Each
release is stored in `share/shuttle/<tag>` under the prefix, and `bin/shuttle`
under the prefix is a link to that release.

Two environment variables change what it does. Set them on the shell that
receives the pipe:

| variable | default | effect |
|---|---|---|
| `STACK_VERSION` | the latest stable release | install this tag, for example `v0.9.1` |
| `STACK_INSTALL_ROOT` | `~/.local` | install under this prefix; put its `bin` directory on `PATH` |

```sh
curl -fsSL https://raw.githubusercontent.com/intigraph/shuttle/main/install.sh |
  STACK_VERSION=v0.9.1 STACK_INSTALL_ROOT="$HOME/.local" sh
```

## Other routes

| route | use it for |
|---|---|
| `tambo install --tool shuttle` | a stack machine. Tambo installs the release it was reviewed with, and `tambo verify --tool shuttle` runs a real run in a throwaway home. |
| the release wheel with pipx | a pinned install without the shell installer. |
| `pip install -e .` in a clone | work on Shuttle itself. |

For pipx, download the wheel and its checksums from the
[release page](https://github.com/intigraph/shuttle/releases/latest), check
the wheel, then install it. Replace `0.9.1` with the release you want:

```sh
curl -fLO https://github.com/intigraph/shuttle/releases/download/v0.9.1/shuttle-0.9.1-py3-none-any.whl
curl -fLO https://github.com/intigraph/shuttle/releases/download/v0.9.1/checksums.txt
grep 'shuttle-0.9.1-py3-none-any.whl$' checksums.txt | shasum -a 256 -c
pipx install ./shuttle-0.9.1-py3-none-any.whl
```

## Removal

For a pipx installation, run `pipx uninstall shuttle`.

For the shell installer, name the prefix and the release you installed. Remove
the command link only if it still points to that release, then remove that
release's directory:

```sh
prefix="$HOME/.local"
version=v0.9.1
if [ "$(readlink "$prefix/bin/shuttle")" = "$prefix/share/shuttle/$version/bin/shuttle" ]; then
  rm "$prefix/bin/shuttle"
fi
rm -r "$prefix/share/shuttle/$version"
```

Removal leaves the run log in `~/.local/state/shuttle` and the keys in
`~/.config/shuttle/keys`. Keep the log until it is exported.

## After installing

- [Install and operate](operating.md) has the state paths and Quipu settings.
- [Agent primer](agent-primer.md) is what an agent reads before it advances a run.
- `shuttle prime` reports this machine's workflows and key files.
