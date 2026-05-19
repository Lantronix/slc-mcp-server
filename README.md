# slc-mcp-server

Model Context Protocol (MCP) server for Lantronix SLC console servers. Exposes the SLC REST API as MCP tools so AI assistants can query device status, inspect ports, check firmware, and manage configuration without direct API knowledge.

Supports SLC9000, SLC8000, and EMG series devices.

## Tools

| Tool | Description |
|---|---|
| `get_system_status` | System status and health |
| `get_system_version` | Firmware and software version |
| `get_network_interfaces` | Network interface configurations and status |
| `get_ztp_status` | Zero Touch Provisioning status |
| `get_slc_ports` | All serial port configurations |
| `get_slc_port` | Single port status by port number |
| `get_connections` | Active connections |
| `get_managed_devices` | Managed device inventory |
| `get_managed_device` | Single managed device status |
| `get_cellular_status` | Cellular modem status |
| `get_firmware_version` | Installed firmware version |
| `get_firmware_update_status` | Firmware update progress |
| `check_firmware_updates` | Trigger firmware update check |
| `compare_config` | Diff running config vs. saved config |
| `save_config` | Save running config (requires `confirm=True`) |
| `configure_provider` | Switch credential provider at runtime |

## Install

```bash
git clone https://github.com/keelhaulin/slc-mcp-server
cd slc-mcp-server
pip install -e .
```

Python 3.11+ required.

## Credential Providers

The server supports four credential backends, selected by `SLC_CREDENTIAL_PROVIDER`.

### env (default)

Credentials are read from environment variables. Device IDs are uppercased with non-alphanumeric characters replaced by `_`.

```bash
SLC_CREDENTIAL_PROVIDER=env
SLC_SLC9000_IP=192.168.100.75
SLC_SLC9000_USERNAME=admin
SLC_SLC9000_PASSWORD=yourpassword
```

Call tools with `device_id="slc9000"`. For a single-device setup, use the global fallback:

```bash
SLC_DEFAULT_IP=192.168.100.75
SLC_USERNAME=admin
SLC_PASSWORD=yourpassword
```

### percepxion

Looks up device IP from Percepxion by hostname. Device IDs must match the hostname registered in Percepxion.

```bash
SLC_CREDENTIAL_PROVIDER=percepxion
PERCEPXION_API_URL=https://api.consoleflow.com
PERCEPXION_USERNAME=admin@example.com
PERCEPXION_PASSWORD=yourpassword
```

### vault

Reads from HashiCorp Vault KV v2 at path `slc/{device_id}`. Expects fields `ip`, `username`, `password`.

```bash
SLC_CREDENTIAL_PROVIDER=vault
VAULT_ADDR=https://vault.example.com
VAULT_TOKEN=hvs.yourtoken
```

Requires `hvac`: `pip install hvac`

### aws

Reads from AWS Secrets Manager at `slc/{device_id}`. Uses the standard AWS credential chain (env vars, IAM role, `~/.aws/config`).

```bash
SLC_CREDENTIAL_PROVIDER=aws
AWS_DEFAULT_REGION=us-east-1
```

Requires `boto3`: `pip install boto3`

## Running

```bash
python run_server.py
```

## Claude Desktop Integration

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS, `%APPDATA%\Claude\claude_desktop_config.json` on Windows):

```json
{
  "mcpServers": {
    "slc-mcp-server": {
      "command": "python",
      "args": ["/path/to/slc-mcp-server/run_server.py"],
      "env": {
        "SLC_CREDENTIAL_PROVIDER": "env",
        "SLC_VERIFY_SSL": "false",
        "SLC_SLC9000_IP": "192.168.1.100",
        "SLC_SLC9000_USERNAME": "admin",
        "SLC_SLC9000_PASSWORD": "yourpassword"
      }
    }
  }
}
```

For WSL on Windows, see `config/claude_desktop_config.wsl_windows.example.json`.

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SLC_CREDENTIAL_PROVIDER` | `env` | Credential backend: `env`, `percepxion`, `vault`, `aws` |
| `SLC_VERIFY_SSL` | `false` | Set `true` for CA-signed certs; `false` for self-signed (default for SLC devices) |
| `SLC_REQUEST_TIMEOUT` | `30` | HTTP request timeout in seconds |
| `SLC_API_PATH_PREFIX` | `/api/v2` | API base path |

Copy `.env.example` to `.env` for a full reference.

## Testing

```bash
pip install -e ".[dev]"
python -m pytest tests/ -v
```

52 tests covering providers, HTTP client, session management, tool dispatch, and integration against a fake device server.

## Security Notes

- Credentials are never logged. Tokens live only in process memory.
- `save_config` requires `confirm=True` to prevent accidental writes.
- Sessions are automatically invalidated and re-authenticated on 401.
- SSL verification is off by default because SLC devices ship with self-signed certificates. Set `SLC_VERIFY_SSL=true` if your devices have CA-signed certs.
