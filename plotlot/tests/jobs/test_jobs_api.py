from __future__ import annotations

from datetime import timedelta

from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from plotlot.api.auth_types import Actor, Capability, IdentityRole
from plotlot.api.harness_jobs import (
    actor_for_jobs,
    admin_router,
    job_storage,
    router,
)
from plotlot.harness.job_queue_storage import PostgresJobQueueStorage


def test_production_app_registers_harness_jobs_route() -> None:
    from plotlot.api.main import app

    assert any(getattr(route, "path", None) == "/api/v1/harness/jobs" for route in app.routes)
    assert any(
        getattr(route, "path", None) == "/api/v1/admin/harness/jobs/dead-letters"
        for route in app.routes
    )


async def test_jobs_api_uses_verified_actor_tenant_and_reports_idempotency_conflict(
    job_store: PostgresJobQueueStorage,
) -> None:
    app = FastAPI()
    app.include_router(router)
    app.include_router(admin_router)
    app.dependency_overrides[job_storage] = lambda: job_store
    app.dependency_overrides[actor_for_jobs] = lambda: Actor(
        user_id="verified-analyst",
        tenant_id="tenant_jobs_a",
        role=IdentityRole.ANALYST,
        capabilities=frozenset({Capability.RUN_ANALYSIS, Capability.VIEW_ANALYSIS}),
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        first = await client.post(
            "/api/v1/harness/jobs",
            headers={"Idempotency-Key": "api-key-0000000001"},
            json={"body": {"subject": "redacted-test-subject"}, "max_attempts": 3},
        )
        duplicate = await client.post(
            "/api/v1/harness/jobs",
            headers={"Idempotency-Key": "api-key-0000000001"},
            json={"body": {"subject": "redacted-test-subject"}, "max_attempts": 3},
        )
        conflict = await client.post(
            "/api/v1/harness/jobs",
            headers={"Idempotency-Key": "api-key-0000000001"},
            json={"body": {"subject": "changed-test-subject"}, "max_attempts": 3},
        )
        job_id = first.json()["job_id"]
        fetched = await client.get(f"/api/v1/harness/jobs/{job_id}")
        events = await client.get(
            f"/api/v1/harness/jobs/{job_id}/events",
            params={"after_cursor": 0, "limit": 10},
        )
        cancelled = await client.post(
            f"/api/v1/harness/jobs/{job_id}/cancel",
            json={"reason": "superseded"},
        )
        cancel_conflict = await client.post(
            f"/api/v1/harness/jobs/{job_id}/cancel",
            json={"reason": "already cancelled"},
        )
        replayed = await client.post(
            f"/api/v1/harness/jobs/{job_id}/replay",
            json={"idempotency_key": "api-replay-key-000001"},
        )
        await client.post(
            f"/api/v1/harness/jobs/{replayed.json()['job_id']}/cancel",
            json={"reason": "keep dead-letter probe isolated"},
        )
        dead_created = await client.post(
            "/api/v1/harness/jobs",
            headers={"Idempotency-Key": "api-dead-key-000001"},
            json={"body": {"subject": "dead-test-subject"}, "max_attempts": 1},
        )
        dead_claim = await job_store.claim(
            tenant_id="tenant_jobs_a",
            worker_id="api-dead-worker",
            lease_for=timedelta(seconds=30),
        )
        assert dead_claim is not None
        assert dead_claim.lease_token is not None
        await job_store.fail(
            "tenant_jobs_a",
            dead_claim.job_id,
            dead_claim.lease_token,
            "terminal-test-failure",
        )
        dead_letters = await client.get("/api/v1/admin/harness/jobs/dead-letters")
        requeued = await client.post(
            f"/api/v1/admin/harness/jobs/{dead_created.json()['job_id']}/requeue"
        )

    assert first.status_code == 201
    assert duplicate.status_code == 200
    assert duplicate.json()["job_id"] == first.json()["job_id"]
    assert conflict.status_code == 409
    assert fetched.status_code == 200
    assert events.status_code == 200
    assert events.json()["items"]
    assert cancelled.status_code == 200
    assert cancel_conflict.status_code == 409
    assert replayed.status_code == 201
    assert replayed.json()["replay_of_job_id"] == job_id
    assert dead_letters.status_code == 200
    assert len(dead_letters.json()["items"]) == 1
    assert requeued.status_code == 200


async def test_jobs_api_rejects_missing_verified_actor() -> None:
    app = FastAPI()
    app.include_router(router)
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.post(
            "/api/v1/harness/jobs",
            headers={"Idempotency-Key": "api-key-no-actor-0001"},
            json={"body": {"subject": "redacted-test-subject"}, "max_attempts": 3},
        )
    assert response.status_code == 401
