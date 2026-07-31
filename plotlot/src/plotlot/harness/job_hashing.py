from __future__ import annotations

import hashlib
import json

from pydantic import JsonValue


def body_sha256(body: dict[str, JsonValue]) -> str:
    canonical = json.dumps(
        body,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode()
    return hashlib.sha256(canonical).hexdigest()
