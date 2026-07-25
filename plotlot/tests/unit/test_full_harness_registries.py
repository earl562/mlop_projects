from __future__ import annotations

from plotlot.api.chat import CHAT_TOOLS
from plotlot.api.chat_harness_tool_specs import FULL_HARNESS_CHAT_TOOL_NAMES
from plotlot.harness.contracts import PolicyPermission, SourceLane
from plotlot.harness.full_harness_registry import (
    get_agent_role_spec,
    get_skill_spec,
    get_tool_spec,
    list_agent_role_specs,
    list_skill_specs,
    list_tool_specs,
)
from plotlot.harness.tool_router_handlers import default_tool_handlers


def test_required_full_harness_skills_are_registered() -> None:
    skill_names = {skill.name for skill in list_skill_specs()}

    assert {
        "zoning_research",
        "site_feasibility",
        "comparable_comping",
        "development_underwriting",
        "acquisition_memo",
        "lender_package",
        "claim_verification",
        "construction_budget",
        "training_ingestion",
        "rehabvaluator_training_extraction",
    }.issubset(skill_names)


def test_training_ingestion_skill_declares_source_lane_and_tools() -> None:
    skill = get_skill_spec("training_ingestion")

    assert SourceLane.TRAINING_VIDEO in skill.allowed_source_lanes
    assert "discover_rehabvaluator_video_sections" in skill.allowed_tools
    assert "extract_training_concepts" in skill.allowed_tools
    assert "training_concept" in skill.required_evidence_types


def test_comparable_comping_skill_declares_reconciliation_tools() -> None:
    skill = get_skill_spec("comparable_comping")

    assert SourceLane.PARCEL_PROPERTY in skill.allowed_source_lanes
    assert SourceLane.MARKET_COMPS in skill.allowed_source_lanes
    assert SourceLane.SOUTH_FLORIDA_GIS in skill.allowed_source_lanes
    assert "capture_public_listing_comps" in skill.allowed_tools
    assert "find_comparables" in skill.allowed_tools
    assert "fetch_web_contents" in skill.allowed_tools
    assert "classify_gis_applicability" in skill.allowed_tools
    assert "market_comp" in skill.required_evidence_types


def test_comping_analyst_role_cannot_underwrite_or_export() -> None:
    role = get_agent_role_spec("comping_analyst")

    assert SourceLane.MARKET_COMPS in role.allowed_source_lanes
    assert "capture_public_listing_comps" in role.allowed_tools
    assert "find_comparables" in role.allowed_tools
    assert "run_residual_land_value" not in role.allowed_tools
    assert "generate_lender_package" not in role.allowed_tools
    assert "export_report" in role.prohibited_tools


def test_gis_analyst_role_cannot_use_financial_calculators() -> None:
    role = get_agent_role_spec("gis_analyst")

    assert SourceLane.SOUTH_FLORIDA_GIS in role.allowed_source_lanes
    assert "query_gis_feature_service" in role.allowed_tools
    assert "run_pro_forma" not in role.allowed_tools


def test_tool_specs_capture_policy_and_fixture_metadata() -> None:
    tool = get_tool_spec("query_gis_feature_service")

    assert tool.permission == PolicyPermission.ALLOW
    assert tool.source_lane is SourceLane.SOUTH_FLORIDA_GIS
    assert tool.fixture_name == "miami_dade_zoning_feature_fixture.json"


def test_underwriting_profile_tool_is_registered_for_cost_assumptions_lane() -> None:
    tool = get_tool_spec("load_underwriting_market_profile")
    rental_tool = get_tool_spec("load_rental_market_evidence")
    role = get_agent_role_spec("development_underwriter")

    assert tool.source_lane is SourceLane.COST_ASSUMPTIONS
    assert rental_tool.source_lane is SourceLane.COST_ASSUMPTIONS
    assert "load_rental_market_evidence" in role.allowed_tools
    assert "load_underwriting_market_profile" in role.allowed_tools


def test_agent_and_tool_lists_are_unique() -> None:
    role_names = [role.name for role in list_agent_role_specs()]
    tool_names = [tool.name for tool in list_tool_specs()]

    assert len(role_names) == len(set(role_names))
    assert len(tool_names) == len(set(tool_names))


def test_chat_tool_specs_have_no_duplicate_names() -> None:
    chat_tool_names = [tool["function"]["name"] for tool in CHAT_TOOLS]

    assert len(chat_tool_names) == len(set(chat_tool_names))


def test_full_harness_chat_tools_exist_in_registry_and_router() -> None:
    registered_tool_names = {tool.name for tool in list_tool_specs()}
    routed_tool_names = set(default_tool_handlers())

    assert FULL_HARNESS_CHAT_TOOL_NAMES <= registered_tool_names
    assert FULL_HARNESS_CHAT_TOOL_NAMES <= routed_tool_names
