from hashlib import sha256
from unittest.mock import AsyncMock, patch

import pytest

from plotlot.api.auth_types import Actor, IdentityRole, capabilities_for_role
from plotlot.security.release import ReleaseRevision


def _actor(role: IdentityRole, user_id: str) -> Actor:
    return Actor(
        user_id=user_id,
        tenant_id="tenant-a",
        role=role,
        capabilities=capabilities_for_role(role),
    )


async def test_analyst_cannot_release_their_own_exact_revision(client) -> None:
    digest = sha256(b"synthetic immutable revision").hexdigest()
    revision_id = "revision-self"
    analyst = _actor(IdentityRole.ANALYST, "analyst-a")
    with patch(
        "plotlot.api.security_middleware.get_current_user",
        new=AsyncMock(return_value=analyst.as_request_user()),
    ):
        request_response = await client.post(
            "/api/v1/releases",
            json={
                "analysis_id": "analysis-self",
                "revision_id": revision_id,
                "revision_sha256": digest,
            },
        )
        release_response = await client.post(
            f"/api/v1/releases/{request_response.json()['request_id']}/release"
        )

    assert request_response.status_code == 201
    assert release_response.status_code == 403


async def test_distinct_reviewer_releases_exact_revision_once_with_both_actors_audited(
    client,
) -> None:
    digest = sha256(b"another synthetic immutable revision").hexdigest()
    revision_id = "revision-reviewed"
    analyst = _actor(IdentityRole.ANALYST, "analyst-a")
    reviewer = _actor(IdentityRole.REVIEWER, "reviewer-a")
    with patch(
        "plotlot.api.security_middleware.get_current_user",
        new=AsyncMock(return_value=analyst.as_request_user()),
    ):
        request_response = await client.post(
            "/api/v1/releases",
            json={
                "analysis_id": "analysis-reviewed",
                "revision_id": revision_id,
                "revision_sha256": digest,
            },
        )

    request_id = request_response.json()["request_id"]
    with patch(
        "plotlot.api.security_middleware.get_current_user",
        new=AsyncMock(return_value=reviewer.as_request_user()),
    ):
        release_response = await client.post(f"/api/v1/releases/{request_id}/release")
        duplicate_response = await client.post(f"/api/v1/releases/{request_id}/release")

    assert release_response.status_code == 200
    assert release_response.json() == {
        "request_id": request_id,
        "analysis_id": "analysis-reviewed",
        "revision_id": revision_id,
        "revision_sha256": digest,
        "requested_by": "analyst-a",
        "reviewed_by": "reviewer-a",
        "status": "released",
    }
    assert duplicate_response.status_code == 409


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("analysis_id", "analysis-mutated"),
        ("revision_id", "revision-mutated"),
        ("revision_sha256", "0" * 64),
    ],
)
async def test_mutated_revision_coordinates_are_not_releasable(
    client,
    field: str,
    value: str,
) -> None:
    analyst = _actor(IdentityRole.ANALYST, "analyst-a")
    body = {
        "analysis_id": "analysis-reviewed",
        "revision_id": "revision-reviewed",
        "revision_sha256": sha256(b"another synthetic immutable revision").hexdigest(),
    }
    body[field] = value
    with patch(
        "plotlot.api.security_middleware.get_current_user",
        new=AsyncMock(return_value=analyst.as_request_user()),
    ):
        response = await client.post("/api/v1/releases", json=body)

    assert response.status_code == 403


async def test_revision_head_mutation_invalidates_pending_release_atomically(
    client,
    release_repository,
) -> None:
    digest = sha256(b"another synthetic immutable revision").hexdigest()
    analyst = _actor(IdentityRole.ANALYST, "analyst-a")
    reviewer = _actor(IdentityRole.REVIEWER, "reviewer-a")
    with patch(
        "plotlot.api.security_middleware.get_current_user",
        new=AsyncMock(return_value=analyst.as_request_user()),
    ):
        requested = await client.post(
            "/api/v1/releases",
            json={
                "analysis_id": "analysis-reviewed",
                "revision_id": "revision-reviewed",
                "revision_sha256": digest,
            },
        )

    await release_repository.save_revision(
        ReleaseRevision(
            tenant_id="tenant-a",
            analysis_id="analysis-reviewed",
            revision_id="revision-replaced",
            revision_sha256=sha256(b"replacement revision").hexdigest(),
            is_clean=True,
        )
    )
    with patch(
        "plotlot.api.security_middleware.get_current_user",
        new=AsyncMock(return_value=reviewer.as_request_user()),
    ):
        released = await client.post(f"/api/v1/releases/{requested.json()['request_id']}/release")

    assert released.status_code == 409
