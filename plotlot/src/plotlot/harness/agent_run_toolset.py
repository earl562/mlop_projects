from __future__ import annotations

from plotlot.harness.agent_run_eval_tool import (
    handle_evaluate_agent_run,
    handle_get_agent_run_improvement_summary,
    handle_get_latest_agent_run_eval,
)
from plotlot.harness.agent_run_tool import handle_start_agent_run
from plotlot.harness.agent_run_trace_tool import handle_get_agent_run_trace
from plotlot.harness.lookup_eval_tools import handle_run_lookup_golden_eval_batch
from plotlot.harness.runtime import HarnessRuntime


def register_agent_run_tools(runtime: HarnessRuntime) -> None:
    runtime.register("start_agent_run", handle_start_agent_run)
    runtime.register("get_agent_run_trace", handle_get_agent_run_trace)
    runtime.register("evaluate_agent_run", handle_evaluate_agent_run)
    runtime.register("get_latest_agent_run_eval", handle_get_latest_agent_run_eval)
    runtime.register("get_agent_run_improvement_summary", handle_get_agent_run_improvement_summary)
    runtime.register("run_lookup_golden_eval_batch", handle_run_lookup_golden_eval_batch)
