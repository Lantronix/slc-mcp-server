# Changelog

## [Unreleased]

### Added
- **CyberArk credential provider** (`providers/cyberark.py`): new fifth credential backend for enterprise deployments. Retrieves SLC device credentials from CyberArk Central Credential Provider (CCP) REST API. AppID-only by default; mTLS activates automatically when `CYBERARK_CERT_PATH` and `CYBERARK_KEY_PATH` are set. Device IP pulled from the CyberArk account's Address field, with fallback to `SLC_{KEY}_IP` env vars.
- **CLAUDE.md**: developer context file for Claude Code sessions — documents naming gotchas, port formula, provider guide, and R21 API notes.
- **Dockerfile**: containerized deployment support.
- **LICENSE**: MIT license.

### Fixed
- `registry.py`: corrected Percepxion device lookup from `GET /v3/device/get?id=` to `POST /v3/device/get` with JSON body `{"device_id": [device_id]}`. The old GET form was unsupported by the current Percepxion API and silently returned 404.
- `registry.py`: login now stores and uses both `x-mystq-token` and `x-csrf-token`. The old implementation discarded `csrf_token`, causing 403s on subsequent device lookups.
- `.env.example`: updated `PERCEPXION_API_URL` default from `https://api.consoleflow.com` (legacy alias) to `https://api.percepxion.ai`.
- `configure_provider` tool: `cyberark` added to the valid provider list.
- `README.md`: updated percepxion-mcp-server link to `Lantronix/percepxion-mcp-server`.

### Changed
- R21 API (9.7.0.0R21) review complete. No new endpoints vs R17. Two minor spec clarifications in `/user/login` (example type corrections) and `/ports/{ID}/action` (duplicate path parameter removed). No tool changes required.

## [0.1.0] — initial release

- 33 MCP tools covering the SLC 9000 REST API v2: sessions, system, network, ports, managed devices, cellular, firmware, config management, users
- Credential providers: env, percepxion, vault, aws
- 2FA support: automatic TOTP challenge-response via `pyotp`
- Integration test suite with mocked HTTP (no live device required)
