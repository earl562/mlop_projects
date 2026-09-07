from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, ConfigDict, Field

from plotlot.api.auth_types import Actor
from plotlot.security.release import (
    ReleaseAuthorizationError,
    ReleaseConflictError,
    ReleaseNotFoundError,
    ReleaseRequest,
    ReleaseWorkflow,
    RevisionCoordinate,
    RevisionNotReleasableError,
    SelfReleaseDeniedError,
)
from plotlot.storage.release_repository import PostgresReleaseRepository


router = APIRouter(prefix="/api/v1/releases", tags=["releases"])


class ExternalReleaseRequestBody(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    analysis_id: str = Field(min_length=1)
    revision_id: str = Field(min_length=1)
    revision_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


def get_release_workflow() -> ReleaseWorkflow:
    return ReleaseWorkflow(PostgresReleaseRepository())


ReleaseWorkflowDependency = Annotated[
    ReleaseWorkflow,
    Depends(get_release_workflow),
]


def _request_actor(request: Request) -> Actor:
    actor = getattr(request.state, "actor", None)
    if not isinstance(actor, Actor):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
        )
    return actor


def _response_payload(release_request: ReleaseRequest) -> dict[str, str]:
    revision = release_request.revision
    return {
        "request_id": release_request.request_id,
        "analysis_id": revision.analysis_id,
        "revision_id": revision.revision_id,
        "revision_sha256": revision.revision_sha256,
        "requested_by": release_request.requested_by,
        "reviewed_by": release_request.reviewed_by or "",
        "status": release_request.status,
    }


@router.post("", status_code=status.HTTP_201_CREATED)
async def request_external_release(
    body: ExternalReleaseRequestBody,
    request: Request,
    workflow: ReleaseWorkflowDependency,
) -> dict[str, str]:
    actor = _request_actor(request)
    if actor.tenant_id is None:
        raise HTTPException(status_code=403, detail="Tenant membership required")
    try:
        release_request = await workflow.request_release(
            actor,
            RevisionCoordinate(
                tenant_id=actor.tenant_id,
                analysis_id=body.analysis_id,
                revision_id=body.revision_id,
                revision_sha256=body.revision_sha256,
            ),
        )
    except (ReleaseAuthorizationError, RevisionNotReleasableError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return _response_payload(release_request)


@router.post("/{request_id}/release")
async def release_external_revision(
    request_id: str,
    request: Request,
    workflow: ReleaseWorkflowDependency,
) -> dict[str, str]:
    try:
        release_request = await workflow.release(
            _request_actor(request),
            request_id,
        )
    except (ReleaseAuthorizationError, SelfReleaseDeniedError) as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except ReleaseNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ReleaseConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return _response_payload(release_request)
