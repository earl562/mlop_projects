"""Tests for local OpenAI/Codex OAuth helpers."""

import base64
import json

from plotlot.oauth.openai_auth import (
    StoredOAuthTokens,
    extract_account_id,
    load_tokens,
    save_tokens,
    token_needs_refresh,
)


def _make_jwt(payload: dict) -> str:
    header = base64.urlsafe_b64encode(json.dumps({"alg": "none"}).encode()).decode().rstrip("=")
    body = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return f"{header}.{body}.sig"


class TestOpenAIOAuthHelpers:
    def test_extract_account_id_from_jwt(self):
        token = _make_jwt({"account_id": "acct_123"})
        assert extract_account_id(token) == "acct_123"

    def test_load_tokens_supports_new_shape(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps(
                {
                    "access": _make_jwt({"account_id": "acct_new"}),
                    "refresh": "refresh-123",
                    "expires": 2000000000,
                    "accountId": "acct_new",
                }
            )
        )

        tokens = load_tokens(auth_file)

        assert tokens is not None
        assert tokens.access
        assert tokens.refresh == "refresh-123"
        assert tokens.expires == 2000000000
        assert tokens.accountId == "acct_new"

    def test_load_tokens_supports_legacy_nested_shape(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        auth_file.write_text(
            json.dumps(
                {
                    "tokens": {
                        "access_token": _make_jwt({"account_id": "acct_old"}),
                        "refresh_token": "legacy-refresh",
                        "expires_at": 2000000001,
                    }
                }
            )
        )

        tokens = load_tokens(auth_file)

        assert tokens is not None
        assert tokens.refresh == "legacy-refresh"
        assert tokens.expires == 2000000001
        assert tokens.accountId == "acct_old"

    def test_save_tokens_writes_compatibility_shapes(self, tmp_path):
        auth_file = tmp_path / "auth.json"
        tokens = StoredOAuthTokens(
            access=_make_jwt({"account_id": "acct_save"}),
            refresh="refresh-save",
            expires=2000000002,
            accountId="acct_save",
        )

        save_tokens(tokens, auth_file)
        payload = json.loads(auth_file.read_text())

        assert payload["access"]
        assert payload["refresh"] == "refresh-save"
        assert payload["tokens"]["access_token"] == payload["access"]
        assert payload["tokens"]["refresh_token"] == "refresh-save"

    def test_token_needs_refresh_uses_expiry_skew(self):
        assert token_needs_refresh(StoredOAuthTokens(access="", refresh="r")) is True
        assert token_needs_refresh(StoredOAuthTokens(access="a", refresh="r", expires=1000), now=0) is False
        assert token_needs_refresh(StoredOAuthTokens(access="a", refresh="r", expires=299), now=0) is True
