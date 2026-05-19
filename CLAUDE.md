# slc-mcp-server

FastMCP server exposing SLC console server device APIs as MCP tools. Supports SLC9000, SLC8000, and EMG series.

## Project Layout

```
src/slc_mcp/
  server.py, 16 MCP tools (entry point for FastMCP)
  client.py, HTTP helpers: login, get, post; _ok/_err envelope
  session.py, SessionManager: per-device token cache + re-auth on 401
  providers/
    __init__.py, CredentialProvider ABC, CredentialError, get_provider() factory
    env.py, EnvCredentialProvider (default)
    percepxion.py, PercepxionCredentialProvider (Percepxion API lookup)
    vault.py, VaultCredentialProvider (HashiCorp Vault KV v2)
    aws.py, AWSCredentialProvider (AWS Secrets Manager)
  registry.py, PercepxionRegistry (IP lookup via Percepxion REST)
run_server.py, Thin entry point: `python run_server.py`
tests/, pytest: unit (providers, client, session, server) + integration
config/, Claude Desktop config examples
```

## Running

```bash
pip install -e ".[dev]"
python run_server.py
```

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SLC_CREDENTIAL_PROVIDER` | `env` | Provider: `env`, `percepxion`, `vault`, `aws` |
| `SLC_VERIFY_SSL` | `false` | Set `true` for CA-signed certs |
| `SLC_REQUEST_TIMEOUT` | `30` | Request timeout in seconds |
| `SLC_URL_SCHEME` | `https` | URL scheme; set `http` only for local testing |
| `SLC_API_PATH_PREFIX` | `/api/v2` | API path prefix |

**env provider:** `SLC_{DEVICE_ID}_IP`, `SLC_{DEVICE_ID}_USERNAME`, `SLC_{DEVICE_ID}_PASSWORD`
(device IDs uppercased, non-alphanumeric → `_`)

**percepxion provider:** `PERCEPXION_URL`, `PERCEPXION_USERNAME`, `PERCEPXION_PASSWORD`

**vault provider:** `VAULT_ADDR`, `VAULT_TOKEN`; secrets at `slc/{device_id}`

**aws provider:** standard AWS env/profile; secrets at `slc/{device_id}`

## Testing

```bash
python -m pytest tests/ -v
```

52 tests: 15 provider, 11 client, 6 session, 10 server, 10 integration.

## Key Design Decisions

- `_SCHEME` env var (`SLC_URL_SCHEME`) exists solely so pytest-httpserver (plain HTTP) works in tests without TLS. Production default is `https`.
- `run_server.py` is the entry point, not `slc_mcp.py`, the latter would shadow the `slc_mcp` package.
- `save_config` requires `confirm=True`, explicit guard against accidental writes.
- 401 responses invalidate the session token; the next call re-authenticates automatically.
- Credentials are never logged; tokens live only in process memory.
