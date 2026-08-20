#!/usr/bin/env python3
"""Apply PlotLot consolidation Slice 2 to the exact August 20 feature head.

Target repository:
  earl562/plotlot-v2
Target source branch/head:
  feat/plotlot-production-agentic-harness-mvp
  3059256d54e4ef30446dfbf18493c7e69145c9d8

The patch is deliberately defensive:
- verifies the Git blob SHA of every modified existing file;
- computes and syntax-checks all transformations before writing;
- backs up every overwritten file;
- restores originals if any write or post-write parse fails;
- supports a no-write --dry-run.

Run from the repository root after fast-forwarding cpt-pro:
    python /path/to/apply_plotlot_slice2.py --repo .
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import shutil
from dataclasses import dataclass
from pathlib import Path
from textwrap import dedent

EXPECTED_BLOBS: dict[str, str] = {
    "plotlot/src/plotlot/harness/tool_registry.py": (
        "aad72dc713f8756c0ec0c576f17573dc215790fe"
    ),
    "plotlot/src/plotlot/api/chat.py": (
        "addf6a637c1e79f7f7eecf2131edebf4ab385ab2"
    ),
}

PLAN_RELATIVE_PATH = (
    "docs/superpowers/plans/2026-08-20-plotlot-chat-runtime-consolidation.md"
)
TEST_REGISTRY_RELATIVE_PATH = "plotlot/tests/unit/test_tool_registry_llm_schemas.py"
TEST_CHAT_RELATIVE_PATH = "plotlot/tests/unit/test_chat_runtime_consolidation.py"


@dataclass(frozen=True)
class PreparedFile:
    path: Path
    content: str
    existed: bool
    original: str | None


def git_blob_sha(text: str) -> str:
    """Return the SHA-1 used by Git for a UTF-8 blob."""

    data = text.encode("utf-8")
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()  # noqa: S324 - Git identity


def replace_once(text: str, old: str, new: str, *, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


def replace_between(
    text: str,
    *,
    start: str,
    end: str,
    replacement: str,
    label: str,
) -> str:
    start_index = text.find(start)
    if start_index < 0:
        raise RuntimeError(f"{label}: start marker not found")
    end_index = text.find(end, start_index)
    if end_index < 0:
        raise RuntimeError(f"{label}: end marker not found")
    return text[:start_index] + replacement + text[end_index:]


def read_verified_source(path: Path, expected_blob: str, *, force: bool) -> str:
    if not path.exists():
        raise FileNotFoundError(path)
    text = path.read_text(encoding="utf-8")
    actual = git_blob_sha(text)
    if actual != expected_blob and not force:
        raise RuntimeError(
            f"Refusing to patch {path}: expected Git blob {expected_blob}, "
            f"found {actual}. Fast-forward cpt-pro to feature head 3059256d and retry. "
            "Use --force only after inspecting the source drift."
        )
    return text


def registry_metadata_block() -> str:
    """Metadata and missing schemas inserted beside the canonical contracts."""

    return dedent(
        r'''


# ---------------------------------------------------------------------------
# Canonical model-facing tool metadata
# ---------------------------------------------------------------------------
# ToolContract stays transport-neutral. Chat/OpenAI-compatible presentation
# guidance lives beside it so api/chat.py no longer maintains a second registry.
_LLM_TOOL_DESCRIPTIONS: dict[str, str] = {
    "geocode_address": (
        "Mandatory first step for a new address. Resolve municipality, county, "
        "state, latitude, and longitude before parcel lookup."
    ),
    "lookup_property_info": (
        "Look up the county parcel/assessor record after geocoding. Returns zoning, "
        "lot size, owner, assessed value, and available building facts."
    ),
    "search_zoning_ordinance": (
        "Search PlotLot's indexed ordinance text for the exact parcel zoning district. "
        "Use retrieved source text rather than model memory."
    ),
    "analyze_property": (
        "Authoritative grounded feasibility and deal-analysis engine for one address. "
        "Use it before stating property-specific units, value, fees, risk, or upside."
    ),
    "calculate": (
        "Deterministic arithmetic evaluator. Use it for deal math instead of model math."
    ),
    "analyze_upzoning": (
        "Deterministic subdivision/upzoning value analysis using caller-supplied values. "
        "Never invent per-lot value."
    ),
    "screen_properties": (
        "Batch buy-box screening for a bounded list of candidate addresses, ranked by "
        "the deterministic residual max land offer."
    ),
    "search_municode_live": (
        "Live Municode fallback when indexed ordinance search is insufficient."
    ),
    "discover_open_data_layers": (
        "Discover live ArcGIS/Open Data parcel and zoning layers for a county and point."
    ),
    "web_search": (
        "Last-resort web search for current or official sources not present in PlotLot."
    ),
    "create_spreadsheet": (
        "Create a Google Sheets spreadsheet from explicit headers and rows. External "
        "write approval is required."
    ),
    "create_document": (
        "Create a Google Docs document from supplied content. External write approval "
        "is required."
    ),
    "generate_document": (
        "Generate an internal evidence-backed report artifact from the current research "
        "chain. Accumulated evidence IDs can be supplied by the chat adapter."
    ),
    "search_properties": (
        "Search county property datasets for acquisition leads matching geography, "
        "owner, land use, lot size, value, sale, and age criteria."
    ),
    "filter_dataset": "Filter, sort, summarize, or limit the active lead dataset.",
    "get_dataset_info": (
        "Return record count, fields, sample rows, and statistics for the active dataset."
    ),
    "export_dataset": (
        "Export the active lead dataset to Google Sheets. External write approval is "
        "required."
    ),
}


# Complete contracts that were previously too sparse for a model-facing schema.
_TOOL_INPUT_SCHEMA_OVERRIDES: dict[str, dict[str, Any]] = {
    "analyze_upzoning": {
        "type": "object",
        "properties": {
            "lot_sqft": {"type": "number", "exclusiveMinimum": 0},
            "value_per_lot": {"type": "number", "minimum": 0},
            "purchase_price": {"type": "number", "minimum": 0},
            "entitlement_soft_costs": {"type": "number", "minimum": 0},
            "baseline_yield": {"type": "integer", "minimum": 1},
            "upzoned_yield": {"type": "integer", "minimum": 1},
            "baseline_min_lot_area_sqft": {
                "type": "number",
                "exclusiveMinimum": 0,
            },
            "upzoned_min_lot_area_sqft": {
                "type": "number",
                "exclusiveMinimum": 0,
            },
            "yield_basis": {"type": "string"},
            "min_lot_width_ft": {"type": "number", "exclusiveMinimum": 0},
            "lot_frontage_ft": {"type": "number", "exclusiveMinimum": 0},
            "value_source": {"type": "string", "enum": ["comps", "override"]},
        },
        "required": ["lot_sqft"],
    },
    "web_search": {
        "type": "object",
        "properties": {"query": {"type": "string", "minLength": 1}},
        "required": ["query"],
    },
}


# Chat does not expose every registry tool to the model, but each exposed tool is
 # derived from the same canonical contract.
_CHAT_TOOL_NAMES: tuple[str, ...] = (
    "geocode_address",
    "lookup_property_info",
    "search_zoning_ordinance",
    "analyze_property",
    "calculate",
    "analyze_upzoning",
    "screen_properties",
    "search_municode_live",
    "discover_open_data_layers",
    "web_search",
    "create_spreadsheet",
    "create_document",
    "generate_document",
    "search_properties",
    "filter_dataset",
    "get_dataset_info",
    "export_dataset",
}

def transform_registry(text: str) -> str:
    """Extend the canonical registry with model-facing presentation metadata."""

    after = ''def
get_tool_contract(name: str) -> ToolContract:
    """Return a tool contract or raise KeyError."""

    return _TOOL_CONTRACTS[replace_tool_alias(name())]
'''
    text = replace_once(
        text,
        after,
        after + registry_metadata_block(),
        label="registry metadata insertion",
    )

    before = ''def tool_contract_json(name: str) -> dict[str, Any]:
    """Return a JSON-serializable view of a contract for API/MCP surfaces."""

    replaced_name = replace_tool_alias(name)
    contract = get_tool_contract(replaced_name)
    payload = contract.model_dump()
    payload["name"] = name
    return payload

''
    after_tool_contract_json = ''def replace_tool_alias(name: str) -> str:
    return _TOOL_ALIASES.get(name, name)


def tool_contract_json(name: str) -> dict[str, Any]:
    """Return a JSON-serializable view of a contract for API/MCP surfaces."""

    replaced_name = replace_tool_alias(name)
    contract = get_tool_contract(replaced_name)
    payload = contract.model_dump()
    payload["name"] = name
    return payload

''
    text = replace_once(
        text,
        before,
        after_tool_contract_json,
        label="registry alias ordering",
    )

    text = text + ''def

def model_tool_function(name: str) -> dict[str, Any]:
    """Return an OpenAI-compatible function schema from the canonical contract."""

    contract = get_tool_contract(name)
    schema = contract.input_schema | {}
    if contract.name in _TOOL_INPUT_SCHEMA_OVERRIDES:
        schema = _TOOL_INPUT_SCHEMA_OVERRIDES[contract.name]
    payload = dict(schema)
    properties = dict(payload.get("properties") or {})
    # Approvals are harness state, never a model-generated business argument.
    properties.pop("approval_id", None)
    payload["properties"] = properties
    required = [field for field in payload.get("required", []) if field != "approval_id"]
    if required:
        payload["required"] = required
    elif "required" in payload:
        payload.pop("required")

    return {
        "type": "function",
        "function": {
            "name": name,
            "description": _LLM_TOOL_DESCRIPTIONS.get(contract.name, contract.description),
            "parameters": payload or {"type": "object", "properties": {}},
        },
    }


def list_model_tools(names: tuple[str, ...] | None = None) -> list[dict[str, Any]]:
    """Return model-facing function schemas derived from ToolContract."""

    selected = names or _CHAT_TOOL_NAMES
    return [model_tool_function(name) for name in selected]
''
    return text


def transform_chat(text: str) -> str:
    """Convert chat into a single-runtime transport adapter."""

    import_old = ''from plotlot.harness.policy import HarnessPolicyEngine
from plotlot.harness.tool_registry import get_tool_contract
from plotlot.harness.default_runtime import get_default_runtime
''
    import_new = ''from plotlot.harness.runtime import HarnessRuntime
from plotlot.harness.tool_registry import get_tool_contract, list_model_tools
InstrumentedRuntime = HarnessRuntime
''
    text = replace_once(text, import_old, import_new, label="chat runtime imports")

    text = replace_once(
        text,
        'self._datasets: dict[str, DatasetInfo | None] = {}',
        'self._datasets: dict[str, DatasetInfo | None] = {}\n'
        'self._runtime_dataset_sessions: set[str] = set()'.replace(" ", "") if False els`'',
        label="session runtime dataset state",
    )
    # The compact expression above is intentionally replaced below; this keeps
    # the replacement string visible and avoids trailing whitespace drift.
    text = text.replace(
        "self._runtime_dataset_sessions: set[str] = set()\n",
        "self._runtime_dataset_sessions: set[str] = set()\n",
    )

    has_dataset_old = ''def has_dataset(self, session_id: str) -> bool:
    return bool(self._datasets.get(session_id))
''
    has_dataset_new = ''def has_dataset(self, session_id: str) -> bool:
    return bool(
        self._datasets.get(session_id)
        or session_id in self._runtime_dataset_sessions
    )

def mark_runtime_dataset(self, session_id: str) -> None:
    self._runtime_dataset_sessions.add(session_id)

def clear_runtime_dataset(self, session_id: str) -> None:
    self._runtime_dataset_sessions.discard(session_id)
''
    text = replace_once(text, has_dataset_old, has_dataset_new, label="runtime dataset flag")

    evict_old = ''self._datasets.pop(session_id, None)
self._geocode.pop(session_id, None)''
    evict_new = ''self._datasets.pop(session_id, None)
self._runtime_dataset_sessions.discard(session_id)
self._geocode.pop(session_id, None)''
    text = replace_once(text, evict_old, evict_new, label="session runtime dataset eviction")

    tools_start = "# ------------------------------------------------------------------------\n# Tool definitions for the LLM\n# ------------------------------------------------------------------------\n\n"
    tools_end = "\n\n# Tool groups for dynamic masking (Notion/CloudQuery pattern:\n"
    text = replace_between(
        text,
        start=tools_start,
        end=tools_end,
        replacement=tools_start + "CHAT_TOOLS: list[dict[str, Any]] = list_model_tools()\n+ " + tools_end.lstrip("\n"),
        label="CHAT_TOOLS derivation",
    )

    executor_start = ''async def _execute_geocode(address: str, session_id: str = "") -> str:
''
    executor_end = ''
    return json.dumps({"status": "error", "message": f"Unknown tool: {tool_name}"})


@router.post("/chat")
''
    compat_executors = ''_COMPAT_HANDLER_NAMES = {
    "analyze_property",
    "calculate",
    "analyze_upzoning",
    "screen_properties",
}


_RISK_CONTROLLED_TOOLS = {
    "search_municode_live",
    "discover_open_data_layers",
    "web_search",
    "search_properties",
    "create_spreadsheet",
    "create_document",
    "generate_document",
    "export_dataset",
}


_CHAT_RUNTIME_HANDLERS_REGISTERED = False


def _handler_payload_datasus(fn_name: str, payload: dict) -> str:
    status = str(payload.get("status") or "ok")
    if status in {
        "error",
        "not_found",
        "no_results",
        "not_configured",
        "quota_exceeded",
        "auth_error",
    }:
        return "error"
    if status == "pending_approval":
        return "pending_approval"
    if status == "blocked":
        return "blocked"
    return "complete"


def _chat_runtime_handlers() -> dict[str, Any]:
    async def analyze_property(hargs, context):
        del context
        address = str(args.get("address") or "")
        session_id = str(args.get("_session_id") or "")
        return json.loads(await _execute_analyze_property(address, session_id))

    async def calculate(args, context):
        del context
        return json.loads(_execute_calculate(str(args.get("expression") or "")))

    async def analyze_upzoning(hargs, context):
        del context
        return json.loads(_execute_analyze_upzoning(args))

    async def screen_properties(args, context):
        del context
        return json.loads(await _execute_screen_properties(args))

    return {
        "analyze_property": analyze_property,
        "calculate": calculate,
        "analyze_upzoning": analyze_upzoning,
        "screen_properties": screen_properties,
    }


def _ensure_chat_runtime_handlers() -> None:
    global _CHAT_RUNTIME_HANDLERS_REGISTERED
    if _CHAT_RUNTIME_HANDLERS_REGISTERED:
        return
    runtime = get_default_runtime()
    for name, handler in _chat_runtime_handlers().items():
        if not runtime.has_handler(name):
            runtime.register(name, handler)
    _CHAT_RUNTIME_HANDLERS_REGISTEREß^5éÈZ®Ëkºwµç