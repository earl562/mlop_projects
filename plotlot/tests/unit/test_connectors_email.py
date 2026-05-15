"""Unit tests for SMTP connector endpoints and credential encryption flow."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import plotlot.api.connectors.email as email_connector
from plotlot.api.connectors.email import (
    _DAILY_SESSION_CAP,
    _decrypt,
    _encrypt,
    _get_fernet,
    _provider_hint,
    _reset_daily_count_if_needed,
)
from plotlot.storage.models import ConnectorCredential

SESSION_ID = "smtp-session-001"
SESSION_HEADER = {"X-Session-ID": SESSION_ID}


class InMemoryConnectorSession:
    """Tiny in-memory stand-in for AsyncSession used by connector endpoints."""

    def __init__(self) -> None:
        self.credentials: dict[str, ConnectorCredential] = {}
        self.commit_count = 0

    def add(self, cred: ConnectorCredential) -> None:
        if not getattr(cred, "id", None):
            cred.id = len(self.credentials) + 1
        self.credentials[cred.session_id] = cred

    async def delete(self, cred: ConnectorCredential) -> None:
        self.credentials.pop(cred.session_id, None)

    async def commit(self) -> None:
        self.commit_count += 1


@pytest.fixture
def fernet_key(monkeypatch) -> str:
    """Inject a valid Fernet key into connector settings."""
    from cryptography.fernet import Fernet

    key = Fernet.generate_key().decode()
    monkeypatch.setattr(email_connector.settings, "connector_encryption_key", key)
    return key


@pytest.fixture
def fake_db(fernet_key, monkeypatch) -> InMemoryConnectorSession:
    db = InMemoryConnectorSession()

    async def _fake_get_credential(
        session_id: str, _db: InMemoryConnectorSession
    ) -> ConnectorCredential | None:
        return db.credentials.get(session_id)

    monkeypatch.setattr(email_connector, "_get_credential", _fake_get_credential)
    return db


@pytest.fixture
def connector_client(fake_db: InMemoryConnectorSession):
    app = FastAPI()
    app.include_router(email_connector.router)

    async def _override_get_session() -> InMemoryConnectorSession:
        return fake_db

    app.dependency_overrides[email_connector.get_session] = _override_get_session
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _reset_send_rate_limiter():
    email_connector._send_rate_limiter._requests.clear()
    yield
    email_connector._send_rate_limiter._requests.clear()


def _make_credential(
    *,
    session_id: str,
    smtp_password: str = "app-password-1234",
    smtp_host: str = "smtp.gmail.com",
    smtp_port: int = 587,
    smtp_username: str = "sender@example.com",
    from_name: str = "PlotLot Sender",
    daily_send_count: int = 0,
    reset_hours_ago: int = 1,
) -> ConnectorCredential:
    return ConnectorCredential(
        session_id=session_id,
        smtp_host=smtp_host,
        smtp_port=smtp_port,
        smtp_username=smtp_username,
        smtp_password_enc=_encrypt(_get_fernet(), smtp_password),
        from_name=from_name,
        daily_send_count=daily_send_count,
        send_count_reset_at=datetime.now(timezone.utc) - timedelta(hours=reset_hours_ago),
    )


class TestFernetHelpers:
    def test_encrypt_decrypt_roundtrip(self, fernet_key):
        ciphertext = _encrypt(_get_fernet(), "super-secret")
        assert ciphertext != "super-secret"
        assert _decrypt(_get_fernet(), ciphertext) == "super-secret"

    def test_decrypt_invalid_raises_http_500(self, fernet_key):
        with pytest.raises(HTTPException) as exc_info:
            _decrypt(_get_fernet(), "not-valid-ciphertext")
        assert exc_info.value.status_code == 500

    def test_missing_key_raises_503(self, monkeypatch):
        monkeypatch.setattr(email_connector.settings, "connector_encryption_key", "")
        with pytest.raises(HTTPException) as exc_info:
            _get_fernet()
        assert exc_info.value.status_code == 503


class TestHelperLogic:
    def test_provider_hint(self):
        assert _provider_hint("smtp.gmail.com") == "gmail"
        assert _provider_hint("smtp.office365.com") == "outlook"
        assert _provider_hint("smtp.mail.yahoo.com") == "yahoo"
        assert _provider_hint("smtp.my-company.local") == "custom"

    def test_daily_reset_logic(self, fernet_key):
        cred = _make_credential(session_id=SESSION_ID, daily_send_count=7, reset_hours_ago=30)
        _reset_daily_count_if_needed(cred)
        assert cred.daily_send_count == 0

        cred.daily_send_count = 5
        cred.send_count_reset_at = datetime.now(timezone.utc) - timedelta(hours=2)
        _reset_daily_count_if_needed(cred)
        assert cred.daily_send_count == 5

    def test_daily_cap_constant(self):
        assert _DAILY_SESSION_CAP == 50

    def test_send_rate_limiter_config(self):
        assert email_connector._send_rate_limiter.max_requests == 5
        assert email_connector._send_rate_limiter.window_seconds == 3600


class TestConnectorEndpoints:
    @pytest.mark.parametrize(
        ("method", "path", "body"),
        [
            (
                "post",
                "/api/v1/connectors/email/configure",
                {
                    "provider": "gmail",
                    "smtp_username": "sender@example.com",
                    "smtp_password": "pw",
                },
            ),
            ("get", "/api/v1/connectors/email/status", None),
            ("post", "/api/v1/connectors/email/test", None),
            (
                "post",
                "/api/v1/connectors/email/draft",
                {
                    "owner_name": "Jane Owner",
                    "property_address": "123 Main St, Miami, FL 33101",
                },
            ),
            (
                "post",
                "/api/v1/connectors/email/send",
                {
                    "to_email": "owner@example.com",
                    "subject": "Hello",
                    "body_html": "<p>Hello</p>",
                },
            ),
            ("delete", "/api/v1/connectors/email/disconnect", None),
        ],
    )
    def test_missing_session_header_returns_400(
        self, connector_client: TestClient, method: str, path: str, body: dict | None
    ):
        request_fn = getattr(connector_client, method)
        kwargs = {"json": body} if body is not None else {}
        response = request_fn(path, **kwargs)
        assert response.status_code == 400
        assert "X-Session-ID" in response.json()["detail"]

    def test_configure_stores_encrypted_password_and_status(
        self, connector_client: TestClient, fake_db: InMemoryConnectorSession
    ):
        response = connector_client.post(
            "/api/v1/connectors/email/configure",
            headers=SESSION_HEADER,
            json={
                "provider": "gmail",
                "smtp_username": "sender@example.com",
                "smtp_password": "my-app-password",
                "from_name": "Phat",
            },
        )
        assert response.status_code == 200
        assert response.json()["configured"] is True
        assert response.json()["provider_hint"] == "gmail"

        stored = fake_db.credentials[SESSION_ID]
        assert stored.smtp_password_enc != "my-app-password"
        assert _decrypt(_get_fernet(), stored.smtp_password_enc) == "my-app-password"

        status_resp = connector_client.get(
            "/api/v1/connectors/email/status",
            headers=SESSION_HEADER,
        )
        assert status_resp.status_code == 200
        status_data = status_resp.json()
        assert status_data["configured"] is True
        assert status_data["smtp_username"] == "sender@example.com"
        assert status_data["daily_sends_used"] == 0
        assert status_data["daily_sends_remaining"] == _DAILY_SESSION_CAP

    def test_configure_custom_requires_host(self, connector_client: TestClient):
        response = connector_client.post(
            "/api/v1/connectors/email/configure",
            headers=SESSION_HEADER,
            json={
                "provider": "custom",
                "smtp_username": "sender@example.com",
                "smtp_password": "pw",
            },
        )
        assert response.status_code == 400
        assert "smtp_host is required" in response.json()["detail"]

    def test_test_endpoint_decrypts_stored_password_before_send(
        self, connector_client: TestClient, fake_db: InMemoryConnectorSession, monkeypatch
    ):
        cred = _make_credential(session_id=SESSION_ID, smtp_password="decrypt-me-now")
        fake_db.credentials[SESSION_ID] = cred

        send_mock = AsyncMock(return_value="<msg@test>")
        monkeypatch.setattr(email_connector, "_send_smtp", send_mock)

        response = connector_client.post(
            "/api/v1/connectors/email/test",
            headers=SESSION_HEADER,
        )
        assert response.status_code == 200
        assert response.json()["sent"] is True

        kwargs = send_mock.await_args.kwargs
        assert kwargs["cred"] is cred
        assert kwargs["smtp_password"] == "decrypt-me-now"
        assert kwargs["to_email"] == cred.smtp_username
        assert kwargs["to_name"] == cred.from_name

    def test_draft_requires_configured_connector(self, connector_client: TestClient):
        response = connector_client.post(
            "/api/v1/connectors/email/draft",
            headers=SESSION_HEADER,
            json={
                "owner_name": "Jane Owner",
                "property_address": "123 Main St, Miami, FL 33101",
            },
        )
        assert response.status_code == 404
        assert "Configure the email connector" in response.json()["detail"]

    def test_draft_success_parses_json_response(
        self, connector_client: TestClient, fake_db: InMemoryConnectorSession, monkeypatch
    ):
        import anthropic

        fake_db.credentials[SESSION_ID] = _make_credential(session_id=SESSION_ID)

        class FakeMessages:
            def create(self, **kwargs):
                assert kwargs["model"] == "claude-sonnet-4-6"
                return SimpleNamespace(
                    content=[
                        SimpleNamespace(
                            text=(
                                "```json\n"
                                '{"subject":"Interested in 123 Main St",'
                                '"body_html":"<p>Hello Jane,</p>",'
                                '"body_text":"Hello Jane,"}'
                                "\n```"
                            )
                        )
                    ]
                )

        class FakeAnthropic:
            def __init__(self, api_key: str):
                self.api_key = api_key
                self.messages = FakeMessages()

        monkeypatch.setattr(anthropic, "Anthropic", FakeAnthropic)

        response = connector_client.post(
            "/api/v1/connectors/email/draft",
            headers=SESSION_HEADER,
            json={
                "owner_name": "Jane Owner",
                "property_address": "123 Main St, Miami, FL 33101",
                "zoning_district": "T5",
                "max_units": 8,
                "sender_name": "Phat",
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["subject"] == "Interested in 123 Main St"
        assert body["body_html"] == "<p>Hello Jane,</p>"
        assert body["body_text"] == "Hello Jane,"

    def test_send_increments_counter_and_uses_decrypted_password(
        self, connector_client: TestClient, fake_db: InMemoryConnectorSession, monkeypatch
    ):
        cred = _make_credential(session_id=SESSION_ID, smtp_password="send-secret")
        fake_db.credentials[SESSION_ID] = cred

        send_mock = AsyncMock(return_value="<send@msg>")
        rate_limit_check = AsyncMock(return_value=None)
        monkeypatch.setattr(email_connector, "_send_smtp", send_mock)
        monkeypatch.setattr(email_connector._send_rate_limiter, "check", rate_limit_check)

        response = connector_client.post(
            "/api/v1/connectors/email/send",
            headers=SESSION_HEADER,
            json={
                "to_email": "owner@example.com",
                "to_name": "Jane Owner",
                "subject": "Regarding your property",
                "body_html": "<p>Hello Jane</p>",
                "body_text": "Hello Jane",
            },
        )
        assert response.status_code == 200
        payload = response.json()
        assert payload["sent"] is True
        assert payload["daily_sends_used"] == 1

        assert cred.daily_send_count == 1
        assert fake_db.commit_count == 1
        assert send_mock.await_args.kwargs["smtp_password"] == "send-secret"
        rate_limit_check.assert_awaited_once()

    def test_send_rejects_when_daily_cap_reached(
        self, connector_client: TestClient, fake_db: InMemoryConnectorSession, monkeypatch
    ):
        cred = _make_credential(
            session_id=SESSION_ID,
            daily_send_count=_DAILY_SESSION_CAP,
        )
        fake_db.credentials[SESSION_ID] = cred
        monkeypatch.setattr(
            email_connector._send_rate_limiter, "check", AsyncMock(return_value=None)
        )

        response = connector_client.post(
            "/api/v1/connectors/email/send",
            headers=SESSION_HEADER,
            json={
                "to_email": "owner@example.com",
                "subject": "Regarding your property",
                "body_html": "<p>Hello</p>",
            },
        )
        assert response.status_code == 429
        assert "Daily session send limit reached" in response.json()["detail"]

    def test_disconnect_removes_credentials(
        self, connector_client: TestClient, fake_db: InMemoryConnectorSession
    ):
        fake_db.credentials[SESSION_ID] = _make_credential(session_id=SESSION_ID)

        response = connector_client.delete(
            "/api/v1/connectors/email/disconnect",
            headers=SESSION_HEADER,
        )
        assert response.status_code == 204
        assert SESSION_ID not in fake_db.credentials
        assert fake_db.commit_count == 1
