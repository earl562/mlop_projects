# /// script
# requires-python = ">=3.12"
# dependencies = [
#   "asyncpg>=0.29",
#   "cryptography>=48.0.1",
#   "pyjwt>=2.13.0",
# ]
# ///

import argparse
import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

import asyncpg
import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt.algorithms import RSAAlgorithm


_IDENTITIES = {
    "tenant_a_owner": ("tenant-a-owner", "tenant-a", "owner"),
    "tenant_a_admin": ("tenant-a-admin", "tenant-a", "admin"),
    "tenant_a_analyst": ("tenant-a-analyst", "tenant-a", "analyst"),
    "tenant_a_reviewer": ("tenant-a-reviewer", "tenant-a", "reviewer"),
    "tenant_a_viewer": ("tenant-a-viewer", "tenant-a", "viewer"),
    "tenant_b_analyst": ("tenant-b-analyst", "tenant-b", "analyst"),
}


def _required_environment(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"{name} is required")
    return value


def _state_dir() -> Path:
    path = Path(_required_environment("PLOTLOT_AUTH_FIXTURE_DIR")).resolve()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)
    return path


def _write_private(path: Path, content: bytes) -> None:
    path.write_bytes(content)
    path.chmod(0o600)


def _write_json(path: Path, content: object, mode: int) -> None:
    path.write_text(json.dumps(content, indent=2, sort_keys=True) + "\n")
    path.chmod(mode)


def prepare() -> None:
    state_dir = _state_dir()
    issuer = _required_environment("PLOTLOT_AUTH_FIXTURE_ISSUER")
    audience = _required_environment("PLOTLOT_AUTH_FIXTURE_AUDIENCE")
    authorized_party = _required_environment("PLOTLOT_AUTH_FIXTURE_AZP")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    kid = f"plotlot-local-{uuid4().hex}"
    jwk = RSAAlgorithm.to_jwk(key.public_key(), as_dict=True)
    jwk.pop("key_ops", None)
    jwk.update({"kid": kid, "use": "sig", "alg": "RS256"})
    now = datetime.now(timezone.utc)
    tokens = {}
    for name, (user_id, tenant_id, role) in _IDENTITIES.items():
        claims = {
            "sub": user_id,
            "org_id": tenant_id,
            "org_role": f"org:{role}",
            "email": f"{user_id}@example.invalid",
            "iss": issuer,
            "aud": audience,
            "azp": authorized_party,
            "jti": f"{name}-{uuid4().hex}",
            "iat": now,
            "nbf": now - timedelta(seconds=5),
            "exp": now + timedelta(hours=2),
        }
        tokens[name] = jwt.encode(
            claims,
            private_pem,
            algorithm="RS256",
            headers={"kid": kid},
        )

    _write_private(state_dir / "private.pem", private_pem)
    _write_json(state_dir / "jwks.json", {"keys": [jwk]}, 0o644)
    _write_json(state_dir / "tokens.json", tokens, 0o600)
    print(f"local auth fixture prepared: {state_dir}")
    print("token values withheld; tokens.json mode=0600")


async def seed() -> None:
    admin_url = _required_environment(
        "PLOTLOT_AUTH_FIXTURE_ADMIN_DATABASE_URL"
    )
    connection = await asyncpg.connect(admin_url)
    try:
        await connection.executemany(
            """INSERT INTO workspaces (id, name, owner_user_id)
            VALUES ($1, $2, $3)
            ON CONFLICT (id) DO UPDATE
            SET name=EXCLUDED.name, owner_user_id=EXCLUDED.owner_user_id""",
            [
                ("tenant-a", "Tenant A", "tenant-a-owner"),
                ("tenant-b", "Tenant B", "tenant-b-owner"),
            ],
        )
        await connection.executemany(
            """INSERT INTO workspace_members (id, workspace_id, user_id, role)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (workspace_id, user_id) DO UPDATE
            SET role=EXCLUDED.role""",
            [
                (f"fixture-{name}", tenant_id, user_id, role)
                for name, (user_id, tenant_id, role) in _IDENTITIES.items()
            ],
        )
        digest = sha256(b"browser immutable release revision").hexdigest()
        await connection.execute(
            """INSERT INTO plotlot.analysis_revision_heads
            (tenant_id, analysis_id, revision_id, revision_sha256, is_clean)
            VALUES ('tenant-a', 'analysis-reviewed', 'revision-reviewed', $1, true)
            ON CONFLICT (tenant_id, analysis_id) DO UPDATE SET
                revision_id=EXCLUDED.revision_id,
                revision_sha256=EXCLUDED.revision_sha256,
                is_clean=EXCLUDED.is_clean""",
            digest,
        )
        await connection.execute(
            """DELETE FROM plotlot.external_release_requests
            WHERE tenant_id IN ('tenant-a', 'tenant-b')"""
        )
    finally:
        await connection.close()
    print("tenant memberships and immutable release revision seeded")
    print(f"release revision sha256={digest}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("prepare", "seed"))
    args = parser.parse_args()
    if args.command == "prepare":
        prepare()
    else:
        asyncio.run(seed())


if __name__ == "__main__":
    main()
