from hashlib import sha256

import pytest
from httpx import ASGITransport, AsyncClient

from plotlot.api.main import app
from plotlot.api.releases import get_release_workflow
from plotlot.security.release import (
    InMemoryReleaseRepository,
    ReleaseRevision,
    ReleaseWorkflow,
)


@pytest.fixture
async def release_repository():
    repository = InMemoryReleaseRepository()
    await repository.save_revision(
        ReleaseRevision(
            tenant_id="tenant-a",
            analysis_id="analysis-self",
            revision_id="revision-self",
            revision_sha256=sha256(b"synthetic immutable revision").hexdigest(),
            is_clean=True,
        )
    )
    await repository.save_revision(
        ReleaseRevision(
            tenant_id="tenant-a",
            analysis_id="analysis-reviewed",
            revision_id="revision-reviewed",
            revision_sha256=sha256(b"another synthetic immutable revision").hexdigest(),
            is_clean=True,
        )
    )
    return repository


@pytest.fixture
async def client(release_repository):
    repository = release_repository
    workflow = ReleaseWorkflow(repository)

    def release_workflow_override() -> ReleaseWorkflow:
        return workflow

    app.dependency_overrides[get_release_workflow] = release_workflow_override
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as http_client:
            yield http_client
    finally:
        app.dependency_overrides.pop(get_release_workflow, None)
