# Setup Instructions

## Prerequisites

- Python 3.11+
- pip / uv

## Install

```bash
git clone https://github.com/Lantronix/slc-mcp-server
cd slc-mcp-server
pip install -e ".[dev]"
```

## Configure

Copy `.env.example` to `.env` and fill in your device credentials:

```bash
cp .env.example .env
```

## Verify

```bash
python -m pytest tests/ -v
python run_server.py
```

The server prints to stderr on startup. If it exits immediately, check that `fastmcp` is installed.

## Claude Desktop Integration

### macOS / Linux

Copy `config/claude_desktop_config.example.json` content into your Claude Desktop config at:
`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS)
`~/.config/Claude/claude_desktop_config.json` (Linux)

Update the `command` path to the absolute path of `run_server.py` on your system.

### Windows (WSL)

Use `config/claude_desktop_config.wsl_windows.example.json` instead. Replace `YOUR_USERNAME` with your Windows username. Claude Desktop runs on Windows but the server runs inside WSL.

Config location on Windows:
`%APPDATA%\Claude\claude_desktop_config.json`

## Credential Providers

### env (default)

Set per-device env vars. Device IDs are uppercased with non-alphanumeric characters replaced by `_`:

```
SLC_SLC9000_IP=192.168.100.75
SLC_SLC9000_USERNAME=admin
SLC_SLC9000_PASSWORD=password
```

Then call tools with `device_id="slc9000"`.

Any username, password or TOTP secret variable also accepts a `_FILE` form that reads the value from the first line of a file, for Docker or Kubernetes secrets:

```
SLC_SLC9000_PASSWORD_FILE=/run/secrets/slc9000_password
```

Set either the variable or its `_FILE` form, not both.

### percepxion

```
SLC_CREDENTIAL_PROVIDER=percepxion
PERCEPXION_URL=https://api.consoleflow.com
PERCEPXION_USERNAME=admin@example.com
PERCEPXION_PASSWORD=your-password
```

Device IDs must match the hostname registered in Percepxion.

### vault

```
SLC_CREDENTIAL_PROVIDER=vault
VAULT_ADDR=https://vault.example.com
VAULT_TOKEN=hvs.your-token
```

Secrets expected at path `slc/{device_id}` with fields `ip`, `username`, `password`.

### aws

```
SLC_CREDENTIAL_PROVIDER=aws
AWS_DEFAULT_REGION=us-east-1
# standard AWS credential chain (env, ~/.aws/credentials, IAM role)
```

Secrets expected in Secrets Manager at name `slc/{device_id}` with JSON fields `ip`, `username`, `password`.

### azure

```
SLC_CREDENTIAL_PROVIDER=azure
AZURE_KEYVAULT_URL=https://my-vault.vault.azure.net
# AZURE_KEYVAULT_SECRET_PREFIX=slc-
```

Install the extra: `pip install -e ".[azure]"`. Store one secret per device named `slc-{device_id}` (characters other than letters, digits and `-` become `-`), holding JSON fields `ip`, `username`, `password` and optionally `totp_secret`:

```
az keyvault secret set --vault-name my-vault --name slc-slc9000 --file slc9000.json
```

The server authenticates with `DefaultAzureCredential` (managed identity, workload identity, service principal variables, or `az login`). Grant that identity the **Key Vault Secrets User** role on the vault.

### command

```
SLC_CREDENTIAL_PROVIDER=command
SLC_CREDENTIAL_COMMAND=/usr/local/bin/slc-creds {device_id}
```

Works with any secrets manager that has a CLI. `{device_id}` is replaced with the device_id, and the command also gets `SLC_DEVICE_ID` in its environment. It must print a JSON object with `ip`, `username`, `password` and optionally `totp_secret`. It runs without a shell, so wrap pipes or variable expansion in a script. `SLC_CREDENTIAL_COMMAND_TIMEOUT` defaults to 30 seconds.

## Switching Providers at Runtime

Call the `configure_provider` tool from Claude with one of: `env`, `percepxion`, `vault`, `aws`, `azure`, `cyberark`, `command`.
This clears all cached sessions and reloads credentials on the next device call.
