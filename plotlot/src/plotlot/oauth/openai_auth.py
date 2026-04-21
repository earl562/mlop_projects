"""OpenAI ChatGPT/Codex OAuth helpers for local PlotLot development.

Supports:
- PKCE auth-code bootstrap flow for public clients
- localhost callback capture with manual paste fallback
- refresh-token based access-token renewal
- token storage compatible with PlotLot config loading
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import secrets
import threading
import time
import webbrowser
from dataclasses import asdict, dataclass
from datetime import datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

DEFAULT_AUTHORIZE_URL = "https://auth.openai.com/oauth/authorize"
DEFAULT_TOKEN_URL = "https://auth.openai.com/oauth/token"
DEFAULT_REDIRECT_URI = "http://127.0.0.1:1455/auth/callback"
DEFAULT_SCOPE = "openid offline_access"
DEFAULT_AUTH_FILE = Path.home() / ".codex" / "auth.json"
EXPIRY_SKEW_SECONDS = 300


@dataclass
class StoredOAuthTokens:
    access: str
    refresh: str = ""
    expires: int | None = None
    accountId: str = ""


def _b64url_encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("utf-8").rstrip("=")


def generate_pkce_pair() -> tuple[str, str]:
    verifier = _b64url_encode(secrets.token_bytes(32))
    challenge = _b64url_encode(hashlib.sha256(verifier.encode("utf-8")).digest())
    return verifier, challenge


def _decode_jwt_payload(token: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        decoded = base64.urlsafe_b64decode(payload + padding)
        parsed = json.loads(decoded.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def extract_account_id(access_token: str) -> str:
    claims = _decode_jwt_payload(access_token)
    for key in ("account_id", "accountId", "acct", "sub"):
        value = claims.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def default_auth_file() -> Path:
    return DEFAULT_AUTH_FILE


def _normalize_expires(value: Any) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str) and value.strip():
        raw = value.strip()
        if raw.isdigit():
            return int(raw)
        try:
            return int(datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp())
        except ValueError:
            return None
    return None


def load_tokens(auth_file: Path | None = None) -> StoredOAuthTokens | None:
    path = auth_file or default_auth_file()
    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text())
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    tokens = data.get("tokens") if isinstance(data.get("tokens"), dict) else data
    if not isinstance(tokens, dict):
        return None

    access = tokens.get("access") or tokens.get("access_token") or ""
    refresh = tokens.get("refresh") or tokens.get("refresh_token") or ""
    expires = _normalize_expires(
        tokens.get("expires") or tokens.get("expires_at") or tokens.get("expiry")
    )
    account_id = tokens.get("accountId") or tokens.get("account_id") or ""

    if not account_id and isinstance(access, str) and access:
        account_id = extract_account_id(access)

    if not isinstance(access, str) or not access.strip():
        if not isinstance(refresh, str) or not refresh.strip():
            return None
        access = ""

    return StoredOAuthTokens(
        access=access.strip(),
        refresh=refresh.strip() if isinstance(refresh, str) else "",
        expires=expires,
        accountId=account_id.strip() if isinstance(account_id, str) else "",
    )


def save_tokens(tokens: StoredOAuthTokens, auth_file: Path | None = None) -> Path:
    path = auth_file or default_auth_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **asdict(tokens),
        "tokens": {
            "access_token": tokens.access,
            "refresh_token": tokens.refresh,
            "expires_at": tokens.expires,
            "account_id": tokens.accountId,
        },
        "updated_at": int(time.time()),
    }
    path.write_text(json.dumps(payload, indent=2) + "\n")
    return path


def has_saved_tokens(auth_file: Path | None = None) -> bool:
    tokens = load_tokens(auth_file)
    return bool(tokens and (tokens.access or tokens.refresh))


def token_needs_refresh(tokens: StoredOAuthTokens, *, now: int | None = None) -> bool:
    if not tokens.access:
        return bool(tokens.refresh)
    if tokens.expires is None:
        return False
    current_time = now if now is not None else int(time.time())
    return current_time >= (tokens.expires - EXPIRY_SKEW_SECONDS)


async def exchange_authorization_code(
    *,
    client_id: str,
    code: str,
    code_verifier: str,
    redirect_uri: str,
    token_url: str = DEFAULT_TOKEN_URL,
) -> StoredOAuthTokens:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "authorization_code",
                "client_id": client_id,
                "code": code,
                "code_verifier": code_verifier,
                "redirect_uri": redirect_uri,
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()

    access = str(payload.get("access_token") or "").strip()
    refresh = str(payload.get("refresh_token") or "").strip()
    expires_in = payload.get("expires_in")
    expires = int(time.time()) + int(expires_in) if expires_in is not None else None
    account_id = extract_account_id(access)
    return StoredOAuthTokens(access=access, refresh=refresh, expires=expires, accountId=account_id)


async def refresh_access_token(
    *,
    client_id: str,
    refresh_token: str,
    token_url: str = DEFAULT_TOKEN_URL,
) -> StoredOAuthTokens:
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "client_id": client_id,
                "refresh_token": refresh_token,
            },
            headers={"Accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()

    access = str(payload.get("access_token") or "").strip()
    refresh = str(payload.get("refresh_token") or refresh_token).strip()
    expires_in = payload.get("expires_in")
    expires = int(time.time()) + int(expires_in) if expires_in is not None else None
    account_id = extract_account_id(access)
    return StoredOAuthTokens(access=access, refresh=refresh, expires=expires, accountId=account_id)


async def get_valid_access_token(
    *,
    client_id: str,
    auth_file: Path | None = None,
    token_url: str = DEFAULT_TOKEN_URL,
) -> str:
    tokens = load_tokens(auth_file)
    if tokens is None:
        return ""
    if not token_needs_refresh(tokens):
        return tokens.access
    if not tokens.refresh:
        return tokens.access

    refreshed = await refresh_access_token(
        client_id=client_id,
        refresh_token=tokens.refresh,
        token_url=token_url,
    )
    save_tokens(refreshed, auth_file)
    return refreshed.access


def build_authorize_url(
    *,
    client_id: str,
    redirect_uri: str,
    code_challenge: str,
    state: str,
    scope: str = DEFAULT_SCOPE,
    authorize_url: str = DEFAULT_AUTHORIZE_URL,
) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
    )
    return f"{authorize_url}?{query}"


class _CallbackHandler(BaseHTTPRequestHandler):
    server_version = "PlotLotOAuth/1.0"
    oauth_code: str | None = None
    oauth_state: str | None = None
    oauth_error: str | None = None

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path != "/auth/callback":
            self.send_response(404)
            self.end_headers()
            return

        query = parse_qs(parsed.query)
        self.__class__.oauth_code = query.get("code", [None])[0]
        self.__class__.oauth_state = query.get("state", [None])[0]
        self.__class__.oauth_error = query.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(
            b"<html><body><h1>PlotLot OAuth complete</h1><p>You can close this tab.</p></body></html>"
        )

    def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
        return


def _wait_for_callback(redirect_uri: str, timeout_seconds: int = 120) -> tuple[str | None, str | None]:
    parsed = urlparse(redirect_uri)
    _CallbackHandler.oauth_code = None
    _CallbackHandler.oauth_state = None
    _CallbackHandler.oauth_error = None
    server = HTTPServer((parsed.hostname or "127.0.0.1", parsed.port or 1455), _CallbackHandler)
    worker = threading.Thread(target=server.handle_request, daemon=True)
    worker.start()
    worker.join(timeout=timeout_seconds)
    server.server_close()
    return _CallbackHandler.oauth_code, _CallbackHandler.oauth_state


def _read_manual_code() -> str:
    value = input("Paste the full redirect URL (or just the authorization code): ").strip()
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        return parse_qs(parsed.query).get("code", [""])[0].strip()
    return value


async def run_pkce_login(
    *,
    client_id: str,
    auth_file: Path,
    authorize_url: str = DEFAULT_AUTHORIZE_URL,
    token_url: str = DEFAULT_TOKEN_URL,
    redirect_uri: str = DEFAULT_REDIRECT_URI,
    scope: str = DEFAULT_SCOPE,
) -> Path:
    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(24)
    url = build_authorize_url(
        client_id=client_id,
        redirect_uri=redirect_uri,
        code_challenge=challenge,
        state=state,
        scope=scope,
        authorize_url=authorize_url,
    )

    print("\nOpen this URL to authorize PlotLot with OpenAI:\n")
    print(url)
    print()
    webbrowser.open(url)

    code: str | None = None
    try:
        code, returned_state = _wait_for_callback(redirect_uri)
        if returned_state and returned_state != state:
            raise RuntimeError("OAuth state mismatch")
    except OSError:
        code = None

    if not code:
        code = _read_manual_code()
    if not code:
        raise RuntimeError("No authorization code received")

    tokens = await exchange_authorization_code(
        client_id=client_id,
        code=code,
        code_verifier=verifier,
        redirect_uri=redirect_uri,
        token_url=token_url,
    )
    return save_tokens(tokens, auth_file)


def cli_main() -> None:
    import os
    import sys

    client_id = os.environ.get("OPENAI_OAUTH_CLIENT_ID", "").strip()
    if not client_id:
        print("OPENAI_OAUTH_CLIENT_ID is required.", file=sys.stderr)
        sys.exit(1)

    auth_file = Path(
        os.environ.get("PLOTLOT_CODEX_AUTH_FILE", str(default_auth_file()))
    ).expanduser()
    authorize_url = os.environ.get("OPENAI_OAUTH_AUTHORIZE_URL", DEFAULT_AUTHORIZE_URL).strip()
    token_url = os.environ.get("OPENAI_OAUTH_TOKEN_URL", DEFAULT_TOKEN_URL).strip()
    redirect_uri = os.environ.get("OPENAI_OAUTH_REDIRECT_URI", DEFAULT_REDIRECT_URI).strip()
    scope = os.environ.get("OPENAI_OAUTH_SCOPE", DEFAULT_SCOPE).strip()

    saved = asyncio.run(
        run_pkce_login(
            client_id=client_id,
            auth_file=auth_file,
            authorize_url=authorize_url,
            token_url=token_url,
            redirect_uri=redirect_uri,
            scope=scope,
        )
    )
    print(f"Saved OpenAI OAuth tokens to {saved}")
