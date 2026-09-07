from __future__ import annotations

from dataclasses import dataclass

from plotlot.protocol.base import canonical_sha256
from plotlot.protocol.commands import OpportunityCommandV1
from plotlot.protocol.projections import OpportunityAcceptedV1


@dataclass(frozen=True, slots=True)
class IdempotencyBodyConflictError(Exception):
    tenant_id: str
    idempotency_key: str
    original_sha256: str
    submitted_sha256: str

    def __str__(self) -> str:
        return "idempotency key was already used with a different command body"


@dataclass(frozen=True, slots=True)
class _Receipt:
    command_sha256: str
    response: OpportunityAcceptedV1


def command_sha256(command: OpportunityCommandV1) -> str:
    unsigned_host = command.host.model_copy(update={"request_sha256": "0" * 64})
    unsigned_command = command.model_copy(update={"host": unsigned_host})
    return canonical_sha256(unsigned_command)


class ProtocolIdempotencyRegistry:
    def __init__(self) -> None:
        self._receipts: dict[tuple[str, str], _Receipt] = {}

    def register(
        self,
        command: OpportunityCommandV1,
        response: OpportunityAcceptedV1,
    ) -> OpportunityAcceptedV1:
        submitted_sha256 = command_sha256(command)
        if submitted_sha256 != command.host.request_sha256:
            raise IdempotencyBodyConflictError(
                tenant_id=command.host.tenant_id,
                idempotency_key=command.host.idempotency_key,
                original_sha256=command.host.request_sha256,
                submitted_sha256=submitted_sha256,
            )
        key = (command.host.tenant_id, command.host.idempotency_key)
        receipt = self._receipts.get(key)
        if receipt is None:
            self._receipts[key] = _Receipt(
                command_sha256=submitted_sha256,
                response=response,
            )
            return response
        if receipt.command_sha256 != submitted_sha256:
            raise IdempotencyBodyConflictError(
                tenant_id=command.host.tenant_id,
                idempotency_key=command.host.idempotency_key,
                original_sha256=receipt.command_sha256,
                submitted_sha256=submitted_sha256,
            )
        return receipt.response.model_copy(update={"reused": True})
