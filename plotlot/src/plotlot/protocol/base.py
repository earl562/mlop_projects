from __future__ import annotations

import hashlib
import json

from pydantic import BaseModel, ConfigDict


class ProtocolModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


def canonical_sha256(model: BaseModel, *, exclude: set[str] | None = None) -> str:
    payload = model.model_dump(mode="json", exclude=exclude or set())
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()
