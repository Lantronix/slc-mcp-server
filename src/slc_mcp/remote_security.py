"""Protection for the remote (HTTP) transports.

The server's tools act on console servers with the credentials this server holds,
so anyone who can reach an HTTP transport can use them. Three controls apply to
http, sse and both:

- Bearer-token client authentication (MCP_AUTH_TOKEN or MCP_AUTH_TOKEN_FILE),
  compared in constant time on every request.
- A start-up check: on a non-loopback address the server refuses to start
  without a token unless MCP_ALLOW_UNAUTHENTICATED=1 is set explicitly, and it
  refuses to start without MCP_ALLOWED_HOSTS (DNS-rebinding protection).
- Host and Origin validation (FastMCP's guard, set to validate every request
  when the server listens on a non-loopback address).
"""
from __future__ import annotations

import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from ipaddress import ip_address

logger = logging.getLogger("slc_mcp")

HTTP_TRANSPORTS = ("http", "sse", "both")


class RemoteConfigError(RuntimeError):
    """The remote transport settings are unsafe; the server must not start."""


def is_loopback(host: str) -> bool:
    host = host.strip().strip("[]").lower()
    if host == "localhost":
        return True
    try:
        return ip_address(host).is_loopback
    except ValueError:
        return False


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in ("1", "true", "yes")


def load_auth_token(env: dict[str, str] | None = None) -> str | None:
    """MCP_AUTH_TOKEN, or the first line of the file named by MCP_AUTH_TOKEN_FILE."""
    env = os.environ if env is None else env
    token = (env.get("MCP_AUTH_TOKEN") or "").strip()
    path = (env.get("MCP_AUTH_TOKEN_FILE") or "").strip()
    if not token and path:
        try:
            with open(path, encoding="utf-8") as f:
                token = f.readline().strip()
        except OSError as e:
            raise RemoteConfigError(f"MCP_AUTH_TOKEN_FILE can't be read: {e}") from e
    if token and len(token) < 16:
        raise RemoteConfigError("MCP_AUTH_TOKEN must be at least 16 characters.")
    return token or None


@dataclass
class RemoteSettings:
    transport: str
    host: str
    token: str | None
    allow_unauthenticated: bool = False
    allowed_hosts: list[str] = field(default_factory=list)
    allowed_origins: list[str] = field(default_factory=list)

    @property
    def remote_bind(self) -> bool:
        return not is_loopback(self.host)


def settings_from_env(transport: str, host: str, env: dict[str, str] | None = None) -> RemoteSettings:
    env = os.environ if env is None else env

    def _list(name: str) -> list[str]:
        return [v.strip() for v in (env.get(name) or "").split(",") if v.strip()]

    return RemoteSettings(
        transport=transport,
        host=host,
        token=load_auth_token(env),
        allow_unauthenticated=_truthy(env.get("MCP_ALLOW_UNAUTHENTICATED")),
        allowed_hosts=_list("MCP_ALLOWED_HOSTS"),
        allowed_origins=_list("MCP_ALLOWED_ORIGINS"),
    )


def check_remote_settings(s: RemoteSettings) -> None:
    """Raise RemoteConfigError when the settings would expose the tools unsafely."""
    if s.transport not in HTTP_TRANSPORTS:
        return
    if s.remote_bind and not s.token:
        if not s.allow_unauthenticated:
            raise RemoteConfigError(
                f"MCP_HOST={s.host} is reachable from other hosts and no MCP_AUTH_TOKEN is set. "
                "Set MCP_AUTH_TOKEN (or MCP_AUTH_TOKEN_FILE), bind to 127.0.0.1, or set "
                "MCP_ALLOW_UNAUTHENTICATED=1 to accept the risk."
            )
        logger.warning(
            "SECURITY WARNING: MCP_ALLOW_UNAUTHENTICATED=1. The %s transport on %s has no client "
            "authentication; anyone who can reach it can use every tool with this server's "
            "device credentials.",
            s.transport,
            s.host,
        )
    if s.remote_bind and not s.allowed_hosts:
        raise RemoteConfigError(
            f"MCP_HOST={s.host} is reachable from other hosts, so MCP_ALLOWED_HOSTS is required "
            "(comma-separated host names or addresses clients use to reach this server, "
            "for example mcp.example.com,192.0.2.10). It protects against DNS rebinding."
        )


class BearerAuthMiddleware:
    """Pure ASGI middleware: every HTTP request needs `Authorization: Bearer <token>`."""

    def __init__(self, app, token: str):
        self.app = app
        self._token = token.encode("utf-8")

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = b""
        for name, value in scope.get("headers", []):
            if name == b"authorization":
                supplied = value
                break
        scheme, _, credential = supplied.partition(b" ")
        if scheme.lower() == b"bearer" and hmac.compare_digest(credential.strip(), self._token):
            await self.app(scope, receive, send)
            return
        body = json.dumps({"error": "unauthorized", "message": "A valid bearer token is required."}).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"www-authenticate", b'Bearer realm="slc-mcp"'),
                    (b"content-length", str(len(body)).encode()),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})


@dataclass
class TransportConfig:
    transport: str
    host: str
    port: int
    stateless_http: bool


def transport_from_env(env: dict[str, str] | None = None) -> TransportConfig:
    """MCP_TRANSPORT (stdio, http, sse or both), MCP_HOST, MCP_PORT and MCP_STATELESS_HTTP.

    stdio is the default. The HTTP transports listen on loopback unless MCP_HOST says
    otherwise; any other address needs MCP_AUTH_TOKEN and MCP_ALLOWED_HOSTS.
    """
    env = os.environ if env is None else env
    transport = (env.get("MCP_TRANSPORT") or "stdio").strip().lower()
    raw_port = (env.get("MCP_PORT") or "8770").strip()
    try:
        port = int(raw_port)
    except ValueError as e:
        raise RemoteConfigError("MCP_PORT must be a number.") from e
    if not 1 <= port <= 65535:
        raise RemoteConfigError("MCP_PORT must be between 1 and 65535.")
    return TransportConfig(
        transport=transport,
        host=(env.get("MCP_HOST") or "127.0.0.1").strip(),
        port=port,
        stateless_http=_truthy(env.get("MCP_STATELESS_HTTP")),
    )
