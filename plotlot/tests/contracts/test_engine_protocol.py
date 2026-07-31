from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from plotlot.api.main import app
from plotlot.protocol.commands import (
    AcquisitionProfileV1,
    OpportunityCommandV1,
    OpportunitySubjectV1,
)
from plotlot.protocol.contexts import ActorContextV1, PlotLotHostContextV1
from plotlot.protocol.errors import ProtocolErrorV1
from plotlot.protocol.idempotency import (
    IdempotencyBodyConflictError,
    ProtocolIdempotencyRegistry,
    command_sha256,
)
from plotlot.protocol.projections import EngineRevisionProjectionV1, OpportunityAcceptedV1


def test_engine_protocol_declares_idempotent_create_and_changed_body_conflict() -> None:
    # Given: the production PlotLot OpenAPI document.
    operation = app.openapi()["paths"].get("/api/v1/engine/opportunities", {}).get("post")

    # When: the opportunity command operation is inspected.
    responses = {} if operation is None else operation["responses"]

    # Then: successful reuse and changed-body conflict are explicit transport outcomes.
    assert operation is not None
    assert "200" in responses
    assert "409" in responses


def _command(*, municipality: str = "Miami") -> OpportunityCommandV1:
    submitted_at = datetime(2026, 7, 27, 12, tzinfo=UTC)
    host = PlotLotHostContextV1(
        protocol_version="plotlot-byright.v1",
        tenant_id="tenant_alpha",
        workspace_id="workspace_alpha",
        host_analysis_id="analysis_alpha",
        host_run_id="hostrun_alpha",
        request_id="request_alpha",
        idempotency_key="idem-alpha-000001",
        request_sha256="0" * 64,
        submitted_at=submitted_at,
        deadline_at=submitted_at + timedelta(minutes=10),
    )
    command = OpportunityCommandV1(
        schema_version="OpportunityCommandV1",
        host=host,
        actor=ActorContextV1(
            actor_type="user",
            actor_id="user_alpha",
            tenant_id="tenant_alpha",
            role="analyst",
            capabilities=("analysis:create",),
            verified_at=submitted_at,
            token_id="token_alpha",
        ),
        opportunity=OpportunitySubjectV1(
            external_id="external_alpha",
            address="100 Redacted Avenue, Miami, FL",
            county="miami-dade",
            municipality=municipality,
            development_program_id="program_alpha",
        ),
        acquisition_profile=AcquisitionProfileV1(
            buyer_kind="general-contractor-developer",
            strategy="build-to-sell",
            target_margin_basis_points=2_500,
        ),
        requested_fact_families=(
            "property-identity",
            "local-truth",
            "constraints-capacity",
            "market-evidence",
            "underwriting",
            "opportunity-analysis",
        ),
    )
    return command.model_copy(
        update={"host": host.model_copy(update={"request_sha256": command_sha256(command)})},
    )


def _accepted() -> OpportunityAcceptedV1:
    return OpportunityAcceptedV1(
        schema_version="OpportunityAcceptedV1",
        host_analysis_id="analysis_alpha",
        host_run_id="hostrun_alpha",
        engine_run_id="engrun_alpha",
        engine_revision_id="engrev_alpha",
        revision_number=1,
        processing_status="queued",
        reused=False,
        event_cursor="evtcur_alpha",
    )


def test_same_body_duplicate_reuses_original_engine_identifiers() -> None:
    # Given: one accepted command bound to an idempotency key.
    registry = ProtocolIdempotencyRegistry()
    original = registry.register(_command(), _accepted())

    # When: the exact canonical command is registered again.
    replayed = registry.register(_command(), _accepted())

    # Then: the original engine run and revision are reused.
    assert replayed.engine_run_id == original.engine_run_id
    assert replayed.engine_revision_id == original.engine_revision_id
    assert replayed.reused is True


def test_changed_body_duplicate_conflicts() -> None:
    # Given: one accepted command bound to an idempotency key.
    registry = ProtocolIdempotencyRegistry()
    registry.register(_command(), _accepted())

    # When/Then: the same key is reused with a changed canonical body.
    with pytest.raises(IdempotencyBodyConflictError):
        registry.register(_command(municipality="Miami Gardens"), _accepted())


@pytest.mark.parametrize(
    ("model_name", "mutation"),
    [
        ("unknown version", {"schema_version": "OpportunityCommandV2"}),
        ("host id family loss", {"host_analysis_id": "engrun_wrong"}),
        ("error code drift", {"code": "NEW_UNDECLARED_ERROR"}),
    ],
)
def test_protocol_poison_values_are_rejected(
    model_name: str,
    mutation: dict[str, str],
) -> None:
    # Given: a valid versioned command, acceptance, or error projection.
    command_payload = _command().model_dump(mode="json")
    accepted_payload = _accepted().model_dump(mode="json")
    error_payload = ProtocolErrorV1(
        schema_version="ProtocolErrorV1",
        code="STALE_REVISION",
        category="conflict",
        retryable=False,
        http_status=409,
        message="revision does not match",
        request_id="request_alpha",
        engine_run_id="engrun_alpha",
        engine_revision_id="engrev_alpha",
    ).model_dump(mode="json")

    # When/Then: each incompatible field is rejected by its boundary model.
    if model_name == "unknown version":
        payload = command_payload | mutation
        with pytest.raises(ValidationError):
            OpportunityCommandV1.model_validate(payload)
    elif model_name == "host id family loss":
        payload = accepted_payload | mutation
        with pytest.raises(ValidationError):
            OpportunityAcceptedV1.model_validate(payload)
    else:
        payload = error_payload | mutation
        with pytest.raises(ValidationError):
            ProtocolErrorV1.model_validate(payload)


def test_released_revision_rejects_evidence_loss_and_status_widening() -> None:
    # Given: a released revision with no evidence and incomplete dimensions.
    payload = {
        "schema_version": "EngineRevisionProjectionV1",
        "engine_run_id": "engrun_alpha",
        "engine_revision_id": "engrev_alpha",
        "revision_number": 1,
        "processing_status": "running",
        "readiness_status": "provisional",
        "pricing_status": "unpriced",
        "review_status": "unreviewed",
        "release_status": "released",
        "evidence_ids": [],
        "blocker_codes": [],
        "projection_sha256": "a" * 64,
        "created_at": "2026-07-27T12:00:00Z",
    }

    # When/Then: parsing prevents aggregate status widening.
    with pytest.raises(ValidationError, match="released revision"):
        EngineRevisionProjectionV1.model_validate(payload)


def test_protocol_error_rejects_retryable_string_coercion() -> None:
    # Given: a protocol error whose boolean wire field drifted to a string.
    payload = {
        "schema_version": "ProtocolErrorV1",
        "code": "REQUEST_INVALID",
        "category": "validation",
        "retryable": "false",
        "http_status": 422,
        "message": "Protocol request validation failed.",
        "request_id": "request_retryable_drift",
    }

    # When/Then: Python rejects the same error-field poison as the generated consumer.
    with pytest.raises(ValidationError):
        ProtocolErrorV1.model_validate(payload)


def test_missing_or_unbounded_deadline_is_rejected() -> None:
    # Given: a valid host context serialized at the boundary.
    payload = _command().host.model_dump(mode="json")

    # When/Then: missing and unbounded deadlines both fail closed.
    missing = {key: value for key, value in payload.items() if key != "deadline_at"}
    with pytest.raises(ValidationError):
        PlotLotHostContextV1.model_validate(missing)
    with pytest.raises(ValidationError, match="thirty minutes"):
        PlotLotHostContextV1.model_validate(
            payload
            | {
                "deadline_at": (
                    datetime.fromisoformat(payload["submitted_at"]) + timedelta(minutes=31)
                ).isoformat(),
            },
        )
