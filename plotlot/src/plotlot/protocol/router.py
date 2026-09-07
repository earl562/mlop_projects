from __future__ import annotations

from typing import Annotated, Never

from fastapi import APIRouter, HTTPException, Path, Query, status

from plotlot.protocol.commands import (
    CancelRunCommandV1,
    OpportunityCommandV1,
    ReplayRunCommandV1,
)
from plotlot.protocol.errors import ProtocolErrorV1
from plotlot.protocol.projections import (
    EngineRevisionProjectionV1,
    EngineRunProjectionV1,
    EvidencePageV1,
    EventPageV1,
    OpportunityAcceptedV1,
    ReportProjectionV1,
)


router = APIRouter(prefix="/api/v1/engine", tags=["engine-protocol"])
PROTOCOL_ERROR_STATUS_CODES = (400, 401, 404, 409, 422, 503, 504)
EngineRunPath = Annotated[str, Path(pattern=r"^engrun_[A-Za-z0-9_-]+$")]
EngineRevisionPath = Annotated[str, Path(pattern=r"^engrev_[A-Za-z0-9_-]+$")]
EventCursorQuery = Annotated[str, Query(pattern=r"^evtcur_[A-Za-z0-9_-]+$")]
EvidenceCursorQuery = Annotated[str, Query(pattern=r"^evcur_[A-Za-z0-9_-]+$")]
PageLimitQuery = Annotated[int, Query(ge=1, le=200)]


def _engine_not_implemented() -> Never:
    raise HTTPException(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        detail="ByRight engine composition is not enabled.",
    )


@router.post(
    "/opportunities",
    response_model=OpportunityAcceptedV1,
    responses={code: {"model": ProtocolErrorV1} for code in PROTOCOL_ERROR_STATUS_CODES},
)
async def create_opportunity(command: OpportunityCommandV1) -> OpportunityAcceptedV1:
    del command
    _engine_not_implemented()


@router.get(
    "/runs/{engine_run_id}",
    response_model=EngineRunProjectionV1,
    responses={code: {"model": ProtocolErrorV1} for code in PROTOCOL_ERROR_STATUS_CODES},
)
async def get_engine_run(engine_run_id: EngineRunPath) -> EngineRunProjectionV1:
    del engine_run_id
    _engine_not_implemented()


@router.get(
    "/runs/{engine_run_id}/revisions/{engine_revision_id}",
    response_model=EngineRevisionProjectionV1,
    responses={code: {"model": ProtocolErrorV1} for code in PROTOCOL_ERROR_STATUS_CODES},
)
async def get_engine_revision(
    engine_run_id: EngineRunPath,
    engine_revision_id: EngineRevisionPath,
) -> EngineRevisionProjectionV1:
    del engine_run_id, engine_revision_id
    _engine_not_implemented()


@router.get(
    "/runs/{engine_run_id}/events",
    response_model=EventPageV1,
    responses={code: {"model": ProtocolErrorV1} for code in PROTOCOL_ERROR_STATUS_CODES},
)
async def list_engine_events(
    engine_run_id: EngineRunPath,
    after_cursor: EventCursorQuery,
    limit: PageLimitQuery = 100,
) -> EventPageV1:
    del engine_run_id, after_cursor, limit
    _engine_not_implemented()


@router.get(
    "/runs/{engine_run_id}/evidence",
    response_model=EvidencePageV1,
    responses={code: {"model": ProtocolErrorV1} for code in PROTOCOL_ERROR_STATUS_CODES},
)
async def list_engine_evidence(
    engine_run_id: EngineRunPath,
    cursor: EvidenceCursorQuery,
    limit: PageLimitQuery = 100,
) -> EvidencePageV1:
    del engine_run_id, cursor, limit
    _engine_not_implemented()


@router.get(
    "/runs/{engine_run_id}/report",
    response_model=ReportProjectionV1,
    responses={code: {"model": ProtocolErrorV1} for code in PROTOCOL_ERROR_STATUS_CODES},
)
async def get_engine_report(engine_run_id: EngineRunPath) -> ReportProjectionV1:
    del engine_run_id
    _engine_not_implemented()


@router.post(
    "/runs/{engine_run_id}/cancel",
    response_model=EngineRunProjectionV1,
    responses={code: {"model": ProtocolErrorV1} for code in PROTOCOL_ERROR_STATUS_CODES},
)
async def cancel_engine_run(
    engine_run_id: EngineRunPath,
    command: CancelRunCommandV1,
) -> EngineRunProjectionV1:
    del engine_run_id, command
    _engine_not_implemented()


@router.post(
    "/runs/{engine_run_id}/replay",
    response_model=OpportunityAcceptedV1,
    responses={code: {"model": ProtocolErrorV1} for code in PROTOCOL_ERROR_STATUS_CODES},
)
async def replay_engine_run(
    engine_run_id: EngineRunPath,
    command: ReplayRunCommandV1,
) -> OpportunityAcceptedV1:
    del engine_run_id, command
    _engine_not_implemented()
