# Bunny CLI

A complete command-line interface for [bunny.net](https://bunny.net) - manage CDN, DNS, Storage, and more.

[![PyPI version](https://badge.fury.io/py/bunny-cli.svg)](https://pypi.org/project/bunny-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub](https://img.shields.io/github/stars/afterdarksys/bunny-cli?style=social)](https://github.com/afterdarksys/bunny-cli)

## Features

- **Pull Zones** - Create, manage, and purge CDN pull zones
- **DNS Zones** - Full DNS management with record CRUD operations
- **Storage Zones** - Manage edge storage zones
- **Cache Purging** - Purge URLs or entire zones
- **Statistics** - View bandwidth, requests, and geographic data
- **Cloudflare Migration** - Migrate DNS and CDN from Cloudflare to Bunny
- **Beautiful Output** - Rich terminal formatting with tables and colors

## Installation

Python 3.9 or newer. See [INSTALL.md](INSTALL.md) for upgrades, a from-source install, and uninstall.

```bash
pipx install bunny-cli
```

`pip install bunny-cli` also works.

## Quick Start

1. Get your API key from [bunny.net Account Settings](https://panel.bunny.net/account)

2. Configure the CLI. Prompting keeps the key out of shell history:
```bash
bunny config set-key
bunny config test
```

3. Start using it:
```bash
bunny pullzone list
bunny dns list
bunny storage list
```

## Usage

### Configuration

```bash
# Save an API key (prompted, hidden)
bunny config set-key

# Show the fingerprint and defaults. The key itself is not printed.
bunny config show

# Check that bunny.net accepts the key
bunny config test

# Set defaults used by later commands
bunny config set output_format json
bunny config set default_pull_zone 12345
bunny config unset api_key
```

`output_format` applies to later commands. `--json` on a command forces JSON for that invocation. `BUNNY_OUTPUT_FORMAT=table` (or `json`) overrides the file.

Environment variables override the file but do not get copied into it:

```bash
export BUNNY_API_KEY=your-api-key
```

### Pull Zones (CDN)

```bash
# List all pull zones
bunny pullzone list

# Create a new pull zone
bunny pullzone create my-cdn https://origin.example.com

# Get pull zone details. The id can be omitted when default_pull_zone is set.
bunny pullzone get 12345

# Add a custom hostname
bunny pullzone add-hostname 12345 cdn.example.com

# Request SSL certificate
bunny pullzone ssl 12345 cdn.example.com

# Purge cache
bunny pullzone purge 12345
bunny pullzone purge 12345 --url https://cdn.example.com/file.js
bunny pullzone purge 12345 --tag product-123

# Delete a pull zone
bunny pullzone delete 12345
```

### DNS Zones

```bash
# List all DNS zones
bunny dns list

# Create a new DNS zone
bunny dns create example.com

# Get zone details with all records
bunny dns get 12345

# Add records
bunny dns record add 12345 A www 192.168.1.1
bunny dns record add 12345 CNAME cdn origin.example.com --ttl 3600
bunny dns record add 12345 MX @ mail.example.com --priority 10
bunny dns record add 12345 TXT @ "v=spf1 include:_spf.google.com ~all"

# Update a record
bunny dns record update 12345 67890 --value 192.168.1.2

# Delete a record
bunny dns record delete 12345 67890

# Export and import records as JSON. Import does not delete existing rows.
bunny dns export 12345 -o example.com.json
bunny dns import 12345 example.com.json --play
bunny dns import 12345 example.com.json --exec

# DNS query statistics
bunny dns stats 12345
```

`@` is the zone apex and is sent to the API as an empty name. MX and SRV records require `--priority`. Unknown record types are rejected.

### Storage Zones

```bash
# List storage zones
bunny storage list

# Show available regions
bunny storage regions

# Create a storage zone
bunny storage create my-storage --region NY
bunny storage create my-storage --region DE --replicate NY --replicate SG

# Get storage zone details. Passwords are masked unless --show-secrets or --json.
bunny storage get 12345

# Delete a storage zone
bunny storage delete 12345
```

### Cache Purging

```bash
# Purge a specific URL
bunny purge url https://cdn.example.com/styles.css
bunny purge url https://cdn.example.com/dir/ --exact

# Purge an entire pull zone, or one CDN tag
bunny purge zone 12345
bunny purge tag 12345 product-123

# Purge all pull zones (careful!)
bunny purge all
```

### Statistics

```bash
# View overview
bunny stats overview

# View for specific date range
bunny stats overview --from 2024-01-01 --to 2024-01-31

# View for specific pull zone
bunny stats overview --zone 12345

# View bandwidth usage
bunny stats bandwidth
```

### Global Options

```bash
# Get JSON output from any command
bunny pullzone list --json
bunny dns get 12345 --json

# Use a specific API key for one command
bunny --api-key YOUR_KEY pullzone list

# Get version
bunny --version
```

## Configuration File

The CLI stores configuration in `~/.config/bunny/config.json` with mode `0600`:

```json
{
  "api_key": "your-api-key",
  "output_format": "table",
  "default_pull_zone": "12345"
}
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `BUNNY_API_KEY` | Your bunny.net API key |
| `BUNNY_API_ACCESS_KEY` | Alternative API key variable (for compatibility) |
| `CF_API_TOKEN` | Cloudflare API token (for migration commands) |

## Cloudflare Migration

Migrate your DNS and CDN from Cloudflare to Bunny.net:

```bash
# Set your Cloudflare API token
export CF_API_TOKEN=your-cloudflare-token

# List your Cloudflare zones
bunny cf zones

# Preview DNS migration (dry run)
bunny cf dns <cf-zone-id> <bunny-zone-id> --play

# Execute DNS migration
bunny cf dns <cf-zone-id> <bunny-zone-id> --exec

# Create a pull zone to replace Cloudflare CDN proxy
bunny cf pullzone <cf-zone-id> my-cdn --play
bunny cf pullzone <cf-zone-id> my-cdn --origin https://origin.example.com --exec
```

Options:
- `--play` - Dry run, show what would be migrated
- `--exec` - Actually execute the migration
- `--skip-proxied` - Skip records that are proxied through Cloudflare
- `--skip-ns` / `--include-ns` - Skip NS records (default: skip)

## Development

```bash
# Clone the repo
git clone https://github.com/afterdarksys/bunny-cli.git
cd bunny-cli

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .
mypy src/
```

## Security

The account API key is sent only to `https://api.bunny.net`, and a Cloudflare token only to `https://api.cloudflare.com`. Redirects are refused so the credential is not forwarded to another host. Response bodies are capped. Local origins and link-local addresses are rejected before a pull zone or purge URL is sent.

`bunny config show` prints a SHA-256 fingerprint. Storage passwords are masked in table output. `--json` on storage commands is machine output and includes the password the API returned. Do not record a terminal session of `storage create` or `--show-secrets` if the scrollback is shared.

A key passed as a process argument can still appear in shell history. Prefer `bunny config set-key` with no argument, or `BUNNY_API_KEY`, on shared machines.

## Changelog

### 0.2.0

- Command-line `--api-key` is actually used, and it is not written into the config file when other settings change.
- Config files are stored mode `0600`. Symlinks and corrupt JSON fail closed.
- Unknown DNS types are rejected instead of being stored as `A`. `@` is the apex. MX and SRV require a priority.
- DNS list, storage list, and Cloudflare record/zone list follow pagination.
- Statistics charts that map timestamps to numbers are summed. Storage "date created" reads `DateCreated`.
- `--skip-ns` can be turned off with `--include-ns`.
- New commands: `config test`, `config unset`, `dns export`, `dns import`, `dns stats`, `purge tag`, and purge by CDN tag.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

A product of [After Dark Systems, LLC](https://afterdarksys.com)

Not affiliated with bunny.net - this is a community tool.
