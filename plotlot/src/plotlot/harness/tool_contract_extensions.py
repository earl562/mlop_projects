from __future__ import annotations

from plotlot.harness.agent_run_eval_tool_contract import AGENT_RUN_EVAL_TOOL_CONTRACTS
from plotlot.harness.agent_run_tool_contract import AGENT_RUN_TOOL_CONTRACTS
from plotlot.harness.ingestion_tool_contract import INGESTION_TOOL_CONTRACTS
from plotlot.harness.lookup_eval_tool_contract import LOOKUP_EVAL_TOOL_CONTRACTS
from plotlot.land_use.models import ToolContract


EXTRA_TOOL_CONTRACTS: dict[str, ToolContract] = {
    **INGESTION_TOOL_CONTRACTS,
    **AGENT_RUN_TOOL_CONTRACTS,
    **AGENT_RUN_EVAL_TOOL_CONTRACTS,
    **LOOKUP_EVAL_TOOL_CONTRACTS,
}
