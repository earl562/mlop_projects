from dataclasses import dataclass, replace
from typing import Protocol
from uuid import uuid4

import anyio

from plotlot.api.auth_types import Actor, Capability


@dataclass(frozen=True, slots=True)
class ReleaseRevision:
    tenant_id: str
    analysis_id: str
    revision_id: str
    revision_sha256: str
    is_clean: bool


@dataclass(frozen=True, slots=True)
class RevisionCoordinate:
    tenant_id: str
    analysis_id: str
    revision_id: str
    revision_sha256: str


@dataclass(frozen=True, slots=True)
class ReleaseRequest:
    request_id: str
    revision: ReleaseRevision
    requested_by: str
    reviewed_by: str | None = None
    status: str = "pending"


class ReleaseRepository(Protocol):
    async def get_revision(
        self,
        coordinate: RevisionCoordinate,
    ) -> ReleaseRevision | None: ...

    async def create(self, request: ReleaseRequest) -> ReleaseRequest: ...

    async def get(self, request_id: str) -> ReleaseRequest | None: ...

    async def compare_and_release(
        self,
        request_id: str,
        reviewer_user_id: str,
    ) -> ReleaseRequest | None: ...


@dataclass(frozen=True, slots=True)
class ReleaseAuthorizationError(Exception):
    capability: Capability

    def __str__(self) -> str:
        return f"missing release capability: {self.capability.value}"


@dataclass(frozen=True, slots=True)
class SelfReleaseDeniedError(Exception):
    user_id: str

    def __str__(self) -> str:
        return f"release requester and reviewer must be distinct: {self.user_id}"


@dataclass(frozen=True, slots=True)
class ReleaseConflictError(Exception):
    request_id: str

    def __str__(self) -> str:
        return f"release request is not pending: {self.request_id}"


@dataclass(frozen=True, slots=True)
class ReleaseNotFoundError(Exception):
    request_id: str

    def __str__(self) -> str:
        return f"release request not found: {self.request_id}"


@dataclass(frozen=True, slots=True)
class RevisionNotReleasableError(Exception):
    revision_id: str

    def __str__(self) -> str:
        return f"revision is not clean and releasable: {self.revision_id}"


class InMemoryReleaseRepository:
    def __init__(self) -> None:
        self._requests: dict[str, ReleaseRequest] = {}
        self._revisions: dict[tuple[str, str], ReleaseRevision] = {}
        self._released_revisions: set[tuple[str, str]] = set()
        self._lock = anyio.Lock()

    async def save_revision(self, revision: ReleaseRevision) -> None:
        async with self._lock:
            self._revisions[(revision.tenant_id, revision.analysis_id)] = revision

    async def get_revision(
        self,
        coordinate: RevisionCoordinate,
    ) -> ReleaseRevision | None:
        revision = self._revisions.get((coordinate.tenant_id, coordinate.analysis_id))
        if (
            revision is None
            or revision.revision_id != coordinate.revision_id
            or revision.revision_sha256 != coordinate.revision_sha256
        ):
            return None
        return revision

    async def create(self, request: ReleaseRequest) -> ReleaseRequest:
        async with self._lock:
            key = (request.revision.tenant_id, request.revision.revision_id)
            if key in self._released_revisions:
                raise ReleaseConflictError(request.request_id)
            self._requests[request.request_id] = request
            return request

    async def get(self, request_id: str) -> ReleaseRequest | None:
        return self._requests.get(request_id)

    async def compare_and_release(
        self,
        request_id: str,
        reviewer_user_id: str,
    ) -> ReleaseRequest | None:
        async with self._lock:
            request = self._requests.get(request_id)
            if request is None:
                return None
            key = (request.revision.tenant_id, request.revision.revision_id)
            current = self._revisions.get(
                (request.revision.tenant_id, request.revision.analysis_id)
            )
            if (
                request.status != "pending"
                or key in self._released_revisions
                or current != request.revision
                or not current.is_clean
            ):
                raise ReleaseConflictError(request_id)
            released = replace(
                request,
                reviewed_by=reviewer_user_id,
                status="released",
            )
            self._requests[request_id] = released
            self._released_revisions.add(key)
            return released


class ReleaseWorkflow:
    def __init__(self, repository: ReleaseRepository) -> None:
        self._repository = repository

    async def request_release(
        self,
        actor: Actor,
        coordinate: RevisionCoordinate,
    ) -> ReleaseRequest:
        if Capability.RUN_ANALYSIS not in actor.capabilities:
            raise ReleaseAuthorizationError(Capability.RUN_ANALYSIS)
        if actor.tenant_id is None:
            raise RevisionNotReleasableError(coordinate.revision_id)
        if actor.tenant_id != coordinate.tenant_id:
            raise RevisionNotReleasableError(coordinate.revision_id)
        revision = await self._repository.get_revision(coordinate)
        if revision is None or not revision.is_clean:
            raise RevisionNotReleasableError(coordinate.revision_id)
        request = ReleaseRequest(
            request_id=str(uuid4()),
            revision=revision,
            requested_by=actor.user_id,
        )
        return await self._repository.create(request)

    async def release(self, actor: Actor, request_id: str) -> ReleaseRequest:
        if Capability.RELEASE_EXTERNAL not in actor.capabilities:
            raise ReleaseAuthorizationError(Capability.RELEASE_EXTERNAL)
        request = await self._repository.get(request_id)
        if request is None or request.revision.tenant_id != actor.tenant_id:
            raise ReleaseNotFoundError(request_id)
        if request.requested_by == actor.user_id:
            raise SelfReleaseDeniedError(actor.user_id)
        released = await self._repository.compare_and_release(
            request_id,
            actor.user_id,
        )
        if released is None:
            raise ReleaseNotFoundError(request_id)
        return released
