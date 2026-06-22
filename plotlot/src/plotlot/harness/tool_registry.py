from __future__ import annotations

from typing import Any

from plotlot.harness.core_tool_contract import CORE_TOOL_CONTRACTS
from plotlot.harness.dataset_tool_contract import DATASET_TOOL_CONTRACTS
from plotlot.harness.discovery_tool_contract import DISCOVERY_TOOL_CONTRACTS
from plotlot.harness.document_tool_contract import DOCUMENT_TOOL_CONTRACTS
from plotlot.harness.lookup_eval_history_tool_contract import (
    LOOKUP_EVAL_HISTORY_TOOL_CONTRACTS,
)
from plotlot.harness.ordinance_tool_contract import ORDINANCE_TOOL_CONTRACTS
from plotlot.harness.tool_contract_extensions import EXTRA_TOOL_CONTRACTS
from plotlot.land_use.models import ToolContract, ToolRiskClass


_TOOL_CONTRACTS: dict[str, ToolContract] = {
    **EXTRA_TOOL_CONTRACTS,
    **CORE_TOOL_CONTRACTS,
    **ORDINANCE_TOOL_CONTRACTS,
    **DISCOVERY_TOOL_CONTRACTS,
    **DATASET_TOOL_CONTRACTS,
    **LOOKUP_EVAL_HISTORY_TOOL_CONTRACTS,
    **DOCUMENT_TOOL_CONTRACTS,
}


def get_tool_contract(name: str) -> ToolContract:
    return _TOOL_CONTRACTS[name]


def list_tool_contracts() -> list[ToolContract]:
    return list(_TOOL_CONTRACTS.values())


def tool_exists(name: str) -> bool:
    return name in _TOOL_CONTRACTS


def tool_risk_class(name: str) -> str:
    contract = _TOOL_CONTRACTS.get(name)
    return contract.risk_class if contract else ToolRiskClass.EXECUTION.value


def tool_contract_json(name: str) -> dict[str, Any]:
    contract = get_tool_contract(name)
    return contract.model_dump()
