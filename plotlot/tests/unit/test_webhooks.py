"""Unit tests for webhook-based agent harness integration."""

from __future__ import annotations

import hmac
import hashlib
import json
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from plotlot.api.webhooks import (
    _decrypt,
    _generate_hmac_signature,
    _get_fernet,
    _validate_webhook_request,
    router as webhooks_router,
)
from plotlot.config import settings as app_settings


@pytest.fixture
def fernet_key() -> str:
    """Generate a valid Fernet key for testing."""
    return Fernet.generate_key().decode()


@pytest.fixture(autouse=True)
def mock_encryption_key(fernet_key, monkeypatch):
    """Ensure encryption key is set for all tests."""
    monkeypatch.setattr(app_settings, "connector_encryption_key", fernet_key)


@pytest.fixture
def shared_secret() -> str:
    return "test-webhook-secret-12345"


@pytest.fixture
def encrypted_secret(fernet_key: str, shared_secret: str) -> str:
    """Return an encrypted version of the shared secret."""
    return Fernet(fernet_key.encode()).encrypt(shared_secret.encode()).decode()


@pytest.fixture
def mock_tenant(encrypted_secret: str, shared_secret: str) -> MagicMock:
    """Create a mock WebhookTenant for testing."""
    tenant = MagicMock()
    tenant.id = str(uuid4())
    tenant.tenant_id = "crm-tenant-001"
    tenant.name = "Test CRM"
    tenant.shared_secret_enc = encrypted_secret
    tenant.callback_url = "https://crm.example.com/webhooks/plotlot"
    tenant.is_active = True
    return tenant


def _build_valid_headers(payload: dict, shared_secret: str) -> dict:
    """Build valid HMAC headers for a webhook request."""
    timestamp = datetime.now(timezone.utc).isoformat()
    body = json.dumps(payload)
    message = f"{timestamp}{body}"
    signature = hmac.new(
        shared_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return {
        app_settings.webhook_signature_header: signature,
        app_settings.webhook_timestamp_header: timestamp,
    }


def _create_valid_payload() -> dict:
    """Create a standard webhook trigger payload."""
    return {
        "webhook_id": "wh-external-123",
        "analysis_type": "full_feasibility",
        "property": {
            "address": "123 Main St",
            "city": "Miami",
            "state": "FL",
            "zip": "33101",
        },
        "context": {
            "workspace_id": "ws-001",
            "project_id": "proj-001",
            "site_id": "site-001",
        },
    }


# --- Unit tests for helper functions ---


def test_get_fernet_returns_fernet_instance(fernet_key, monkeypatch):
    monkeypatch.setattr(app_settings, "connector_encryption_key", fernet_key)
    instance = _get_fernet()
    assert isinstance(instance, Fernet)


def test_get_fernet_raises_when_no_key(monkeypatch):
    monkeypatch.setattr(app_settings, "connector_encryption_key", "")
    with pytest.raises(Exception, match="Webhook system not configured"):
        _get_fernet()


def test_decrypt_roundtrips(fernet_key, monkeypatch):
    original = "secret-value-42"
    encrypted = Fernet(fernet_key.encode()).encrypt(original.encode()).decode()
    assert _decrypt(_get_fernet(), encrypted) == original


def test_generate_hmac_signature_produces_hex():
    sig = _generate_hmac_signature("some-secret", "2026-06-07T12:00:00", '{"test": true}')
    assert len(sig) == 64  # SHA256 hex digest
    assert all(c in "0123456789abcdef" for c in sig)


def test_validate_webhook_request_valid(shared_secret):
    """Valid request with correct timestamp and signature."""
    payload = _create_valid_payload()
    headers = _build_valid_headers(payload, shared_secret)
    
    mock_request = MagicMock()
    mock_request.headers = headers
    mock_request.body.return_value = json.dumps(payload).encode()
    
    is_valid, error = _validate_webhook_request(mock_request, shared_secret)
    assert is_valid is True
    assert error == ""


def test_validate_webhook_request_missing_timestamp(shared_secret):
    """Missing timestamp header."""
    mock_request = MagicMock()
    mock_request.headers = {app_settings.webhook_signature_header: "some-sig"}
    
    is_valid, error = _validate_webhook_request(mock_request, shared_secret)
    assert is_valid is False
    assert "Missing" in error


def test_validate_webhook_request_missing_signature(shared_secret):
    """Missing signature header."""
    timestamp = datetime.now(timezone.utc).isoformat()
    mock_request = MagicMock()
    mock_request.headers = {app_settings.webhook_timestamp_header: timestamp}
    
    is_valid, error = _validate_webhook_request(mock_request, shared_secret)
    assert is_valid is False
    assert "Missing" in error


def test_validate_webhook_request_expired_timestamp(shared_secret):
    """Timestamp outside valid window."""
    payload = _create_valid_payload()
    old_timestamp = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
    body = json.dumps(payload)
    message = f"{old_timestamp}{body}"
    signature = hmac.new(
        shared_secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    
    mock_request = MagicMock()
    mock_request.headers = {
        app_settings.webhook_signature_header: signature,
        app_settings.webhook_timestamp_header: old_timestamp,
    }
    mock_request.body.return_value = body.encode()
    
    is_valid, error = _validate_webhook_request(mock_request, shared_secret)
    assert is_valid is False
    assert "Timestamp" in error


def test_validate_webhook_request_invalid_signature(shared_secret):
    """Valid timestamp but wrong signature."""
    timestamp = datetime.now(timezone.utc).isoformat()
    mock_request = MagicMock()
    mock_request.headers = {
        app_settings.webhook_signature_header: "invalid-sig-123",
        app_settings.webhook_timestamp_header: timestamp,
    }
    mock_request.body.return_value = b'{"test": true}'
    
    is_valid, error = _validate_webhook_request(mock_request, shared_secret)
    assert is_valid is False
    assert "signature" in error.lower()


def test_validate_webhook_request_invalid_timestamp_format(shared_secret):
    """Timestamp that can't be parsed."""
    mock_request = MagicMock()
    mock_request.headers = {
        app_settings.webhook_signature_header: "some-sig",
        app_settings.webhook_timestamp_header: "not-a-timestamp",
    }
    
    is_valid, error = _validate_webhook_request(mock_request, shared_secret)
    assert is_valid is False
    assert "Invalid timestamp" in error
