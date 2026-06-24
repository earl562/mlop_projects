from __future__ import annotations

from plotlot.harness.agent_run_toolset import register_agent_run_tools
from plotlot.harness.default_authority_tools import (
    handle_discover_code_authorities,
    handle_discover_municode_authorities,
    handle_discover_open_data_layers,
    handle_search_code_authority_live,
)
from plotlot.harness.default_dataset_tools import (
    handle_export_dataset,
    handle_filter_dataset,
    handle_get_dataset_info,
    handle_search_properties,
)
from plotlot.harness.default_document_tools import (
    handle_create_document,
    handle_create_spreadsheet,
    handle_draft_email,
    handle_draft_google_doc,
    handle_gmail_send_draft,
)
from plotlot.harness.default_location_tools import (
    handle_geocode_address,
    handle_lookup_property_info,
)
from plotlot.harness.default_municode_live_tools import (
    handle_search_municode_live,
    is_pdf_scraped,
)
from plotlot.harness.default_ordinance_tools import (
    handle_fetch_ordinance_section,
    handle_search_ordinances,
    handle_search_zoning_ordinance,
)
from plotlot.harness.default_web_tools import handle_web_search
from plotlot.harness.ingestion_tool import handle_ingest_municipality
from plotlot.harness.lookup_eval_tools import (
    handle_assess_lookup_release_gate,
    handle_list_lookup_eval_runs,
)
from plotlot.harness.policy import HarnessPolicyEngine
from plotlot.harness.report_artifacts import handle_generate_document
from plotlot.harness.runtime import HarnessRuntime
from plotlot.land_use.policy import ToolPolicy

_handle_search_ordinances = handle_search_ordinances
_handle_search_municode_live = handle_search_municode_live
_is_pdf_scraped = is_pdf_scraped


def build_default_runtime() -> HarnessRuntime:
    policy = HarnessPolicyEngine(
        policy=ToolPolicy(
            internal_write_tools=frozenset({"draft_email", "draft_google_doc", "generate_document"})
        )
    )
    runtime = HarnessRuntime(policy=policy)
    runtime.register("ingest_municipality", handle_ingest_municipality)
    runtime.register("geocode_address", handle_geocode_address)
    runtime.register("lookup_property_info", handle_lookup_property_info)
    runtime.register("search_zoning_ordinance", handle_search_zoning_ordinance)
    runtime.register("search_ordinances", handle_search_ordinances)
    runtime.register("fetch_ordinance_section", handle_fetch_ordinance_section)
    runtime.register("search_municode_live", handle_search_municode_live)
    runtime.register("discover_municode_authorities", handle_discover_municode_authorities)
    runtime.register("discover_code_authorities", handle_discover_code_authorities)
    runtime.register("search_code_authority_live", handle_search_code_authority_live)
    runtime.register("discover_open_data_layers", handle_discover_open_data_layers)
    runtime.register("draft_google_doc", handle_draft_google_doc)
    runtime.register("draft_email", handle_draft_email)
    runtime.register("generate_document", handle_generate_document)
    runtime.register("web_search", handle_web_search)
    runtime.register("search_properties", handle_search_properties)
    runtime.register("filter_dataset", handle_filter_dataset)
    runtime.register("get_dataset_info", handle_get_dataset_info)
    register_agent_run_tools(runtime)
    runtime.register("list_lookup_eval_runs", handle_list_lookup_eval_runs)
    runtime.register("assess_lookup_release_gate", handle_assess_lookup_release_gate)
    runtime.register("create_spreadsheet", handle_create_spreadsheet)
    runtime.register("create_document", handle_create_document)
    runtime.register("export_dataset", handle_export_dataset)
    runtime.register("gmail_send_draft", handle_gmail_send_draft)
    return runtime


_DEFAULT_RUNTIME: HarnessRuntime | None = None


def get_default_runtime() -> HarnessRuntime:
    global _DEFAULT_RUNTIME
    if _DEFAULT_RUNTIME is None:
        _DEFAULT_RUNTIME = build_default_runtime()
    return _DEFAULT_RUNTIME
