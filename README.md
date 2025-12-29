# Bunny CLI

A complete command-line interface for [bunny.net](https://bunny.net) - manage CDN, DNS, Storage, and more.

[![PyPI version](https://badge.fury.io/py/bunny-cli.svg)](https://pypi.org/project/bunny-cli/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub](https://img.shields.io/github/stars/straticus1/bunny-cli?style=social)](https://github.com/straticus1/bunny-cli)

## Features

- **Pull Zones** - Create, manage, and purge CDN pull zones
- **DNS Zones** - Full DNS management with record CRUD operations
- **Storage Zones** - Manage edge storage zones
- **Cache Purging** - Purge URLs or entire zones
- **Statistics** - View bandwidth, requests, and geographic data
- **Cloudflare Migration** - Migrate DNS and CDN from Cloudflare to Bunny
- **Beautiful Output** - Rich terminal formatting with tables and colors

## Installation

```bash
pip install bunny-cli
```

Or with [pipx](https://pypa.github.io/pipx/) (recommended for CLI tools):

```bash
pipx install bunny-cli
```

## Quick Start

1. Get your API key from [bunny.net Account Settings](https://panel.bunny.net/account)

2. Configure the CLI:
```bash
bunny config set-key YOUR_API_KEY
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
# Set your API key
bunny config set-key YOUR_API_KEY

# Show current config
bunny config show

# Set defaults
bunny config set output_format json
```

You can also use environment variables:
```bash
export BUNNY_API_KEY=your-api-key
```

### Pull Zones (CDN)

```bash
# List all pull zones
bunny pullzone list

# Create a new pull zone
bunny pullzone create my-cdn https://origin.example.com

# Get pull zone details
bunny pullzone get 12345

# Add a custom hostname
bunny pullzone add-hostname 12345 cdn.example.com

# Request SSL certificate
bunny pullzone ssl 12345 cdn.example.com

# Purge cache
bunny pullzone purge 12345
bunny pullzone purge 12345 --url https://cdn.example.com/file.js

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
```

### Storage Zones

```bash
# List storage zones
bunny storage list

# Show available regions
bunny storage regions

# Create a storage zone
bunny storage create my-storage --region NY
bunny storage create my-storage --region DE --replicate NY --replicate SG

# Get storage zone details
bunny storage get 12345

# Delete a storage zone
bunny storage delete 12345
```

### Cache Purging

```bash
# Purge a specific URL
bunny purge url https://cdn.example.com/styles.css

# Purge entire pull zone
bunny purge zone 12345

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

The CLI stores configuration in `~/.config/bunny/config.json`:

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
- `--skip-ns` - Skip NS records (default: true)

## Development

```bash
# Clone the repo
git clone https://github.com/straticus1/bunny-cli.git
cd bunny-cli

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check .
mypy src/
```

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Credits

A product of [After Dark Systems, LLC](https://afterdarksys.com)

Not affiliated with bunny.net - this is a community tool.
