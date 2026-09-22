# Install Bunny CLI

Bunny CLI needs Python 3.9 or newer. The published package name is `bunny-cli` and the command is `bunny`.

## From PyPI

```bash
pip install bunny-cli
```

`pipx` keeps the command out of the environment you use for other projects:

```bash
pipx install bunny-cli
bunny --version
```

Upgrade with the same tool you installed with:

```bash
pip install --upgrade bunny-cli
# or
pipx upgrade bunny-cli
```

## From this repository

```bash
git clone https://github.com/afterdarksys/bunny-cli.git
cd bunny-cli
python3 -m pip install -e ".[dev]"
bunny --version
pytest
ruff check .
mypy src/
```

An editable install uses the `src/bunny_cli` tree, so local edits are picked up without reinstalling.

## Configure an API key

Create an API key in the [bunny.net account settings](https://panel.bunny.net/account). Prefer the environment for machines and CI:

```bash
export BUNNY_API_KEY="your-api-key"
bunny config test
```

`BUNNY_API_ACCESS_KEY` is accepted as a fallback name. To store a key for an interactive user, prompt for it so the value is not written to shell history:

```bash
bunny config set-key
```

Passing the key as an argument (`bunny config set-key YOUR_KEY` or `bunny --api-key YOUR_KEY ...`) still works. Those forms can show up in shell history and in the process list.

The config file is `~/.config/bunny/config.json`. Bunny CLI creates the directory as mode `0700` and the file as mode `0600`, and tightens a file it finds with broader permissions. A symlinked config file is refused. `bunny config show` prints a SHA-256 fingerprint of the key, not the key.

Check the saved file:

```bash
bunny config path
ls -l ~/.config/bunny/config.json
bunny config test
```

## Useful defaults

```bash
bunny config set output_format json
bunny config set default_pull_zone 12345
bunny config set default_dns_zone 67890
bunny config set default_storage_zone 13579
```

`output_format` is `table` or `json`. For one command, `--json` forces JSON. `BUNNY_OUTPUT_FORMAT=table` or `BUNNY_OUTPUT_FORMAT=json` overrides the file for that process. Default zone ids are used by the read commands (`pullzone get`, `dns get`, `dns export`, `dns stats`, `storage get`) when you omit the id. Delete, purge, and update commands still require an explicit id.

## Uninstall

```bash
pipx uninstall bunny-cli
# or
pip uninstall bunny-cli
rm -rf ~/.config/bunny
```

Removing `~/.config/bunny` deletes the saved API key from this machine.
