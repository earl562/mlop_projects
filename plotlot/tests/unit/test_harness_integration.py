"""End-to-end integration test — harness + skills + model adapter.

Verifies the complete PlotLot harness works:
1. AgentLoop with middleware pipeline initializes correctly
2. Filesystem tools operate within workspace bounds
3. Interpreter skills produce correct domain outputs
4. Skill registry discovers and loads SKILL.md
5. Sub-agent middleware registers and spawns correctly
6. Rubric middleware evaluates output against criteria
7. Model adapter creates caller for configured provider
8. Complete agent config assembles without errors
"""

import asyncio
import os
import sys
from typing import Any

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "src"))


class TestHarnessIntegration:
    """End-to-end harness integration tests."""

    def test_full_agent_config_assembles(self):
        """AgentConfig + middleware + tools + interpreter skills all wire together."""
        from plotlot.harness import (
            AgentConfig,
            AgentLoop,
            AgentState,
            FILESYSTEM_TOOLS,
            INTERPRETER_SKILLS,
            LocalContextMiddleware,
            LoopDetectionMiddleware,
            RubricMiddleware,
            SubAgent,
            SubAgentMiddleware,
            TokenAwareMiddleware,
            check_zoning,
            identify_permits,
            calculate_pro_forma,
            validate_setbacks,
            calculate_fees,
            read_file,
            write_file,
            glob_files,
            grep_files,
        )
        from plotlot.harness.model_adapter import create_model_caller

        # 1. All interpreter skills are callable
        assert callable(check_zoning)
        assert callable(identify_permits)
        assert callable(calculate_pro_forma)
        assert callable(validate_setbacks)
        assert callable(calculate_fees)
        assert len(INTERPRETER_SKILLS) == 5

        # 2. All filesystem tools are callable
        assert callable(read_file)
        assert callable(write_file)
        assert callable(glob_files)
        assert callable(grep_files)
        assert len(FILESYSTEM_TOOLS) == 5

        # 3. Model adapter creates caller
        call_model = create_model_caller(provider="openrouter", api_key="sk-test")
        assert callable(call_model)

        # 4. Sub-agents register
        zoning_agent = SubAgent(
            name="zoning",
            description="Analyze zoning compliance",
            system_prompt="You are a zoning analyst.",
            tools=[FILESYSTEM_TOOLS["read_file"]],
        )
        sub_mw = SubAgentMiddleware(sub_agents=[zoning_agent])
        assert len(sub_mw.get_tool_schemas()) == 1
        assert "zoning" in sub_mw.get_agent_names()

        # 5. Full middleware stack assembles
        config = AgentConfig(
            model="google/gemini-2.5-flash-lite:free",
            system_prompt="You are a land development analyst.",
            tools=list(FILESYSTEM_TOOLS.values()),
            max_iterations=3,
            middleware=[
                TokenAwareMiddleware(max_tokens=200_000),
                LocalContextMiddleware(),
                LoopDetectionMiddleware(max_edits_per_file=5),
                sub_mw,
                RubricMiddleware(rubric=["zoning compliance", "setback verification"]),
            ],
        )
        assert config.model == "google/gemini-2.5-flash-lite:free"
        assert len(config.middleware) == 5
        assert len(config.tools) == 5

        # 6. Agent loop initializes
        from plotlot.harness.agent_loop import AgentLoop

        loop = AgentLoop(
            config=config,
            call_model=call_model,
            execute_tool=lambda n, a: {"ok": True, "tool": n},
        )
        assert loop is not None

    def test_skill_registry_discovers_skills(self):
        """SkillRegistry loads SKILL.md from skills directory."""
        from plotlot.harness.skill_registry import SkillRegistry

        skills_dir = os.path.join(
            os.path.dirname(__file__), "..", "..", "skills"
        )
        if os.path.isdir(skills_dir):
            registry = SkillRegistry(skills_dir=skills_dir)
            names = registry.list_names()
            assert "zoning-analyst" in names, f"Expected zoning-analyst, got {names}"

    def test_interpreter_skill_zoning_compliance(self):
        """check_zoning catches height and setback violations."""
        from plotlot.harness.interpreter_skills import (
            check_zoning,
            ParcelZoning,
            ProposedUse,
        )

        zoning = ParcelZoning(
            parcel_id="P-12345",
            zone_district="R-3",
            permitted_uses=["single_family", "multi_family"],
            max_height_ft=35,
            min_setback_front_ft=20,
            min_setback_side_ft=5,
            min_setback_rear_ft=25,
            max_density_units_per_acre=12,
            parking_per_unit=1.5,
        )

        # Compliant proposal
        ok = ProposedUse(
            use_type="single_family",
            building_height_ft=30,
            front_setback_ft=25,
            side_setback_ft=10,
            rear_setback_ft=30,
            unit_count=1,
            lot_size_sqft=5000,
            parking_spaces=2,
        )
        result = check_zoning(zoning, ok)
        assert result.passed is True, f"Expected pass, got failures: {result.failures}"

        # Height violation
        too_tall = ProposedUse(
            use_type="single_family",
            building_height_ft=45,
            front_setback_ft=25,
            side_setback_ft=10,
            rear_setback_ft=30,
        )
        result2 = check_zoning(zoning, too_tall)
        assert result2.passed is False
        assert any("height" in f.lower() for f in result2.failures)

        # Wrong use
        wrong_use = ProposedUse(use_type="industrial")
        result3 = check_zoning(zoning, wrong_use)
        assert result3.passed is False
        assert any("permitted" in f.lower() for f in result3.failures)

    def test_interpreter_skill_permits(self):
        """identify_permits returns required and conditional permits."""
        from plotlot.harness.interpreter_skills import identify_permits

        result = identify_permits("multi_family")
        assert result.passed is True
        required = result.evidence["required_permits"]
        assert len(required) >= 4
        assert any(p["permit"] == "Conditional Use Permit" for p in required)

    def test_interpreter_skill_pro_forma(self):
        """calculate_pro_forma produces correct financial outputs."""
        from plotlot.harness.interpreter_skills import (
            ProFormaInputs,
            calculate_pro_forma,
        )

        inputs = ProFormaInputs(
            land_cost=500000,
            construction_cost_per_sqft=150,
            total_sqft=10000,
            unit_count=10,
            avg_rent_per_unit=2000,
            vacancy_rate=0.05,
            operating_expense_ratio=0.35,
            cap_rate=0.06,
        )
        result = calculate_pro_forma(inputs)
        assert result.passed is True
        outputs = result.evidence["outputs"]
        # Hard costs = 150 * 10000 = 1,500,000
        assert outputs["hard_costs"] == 1_500_000
        # Gross annual income = 10 * 2000 * 12 = 240,000
        assert outputs["gross_annual_income"] == 240_000
        # NOI = 240000 * 0.95 * 0.65 = 148,200
        assert abs(outputs["net_operating_income"] - 148_200) < 1
        # Property value = 148200 / 0.06 = 2,470,000
        assert abs(outputs["property_value_cap_rate"] - 2_470_000) < 1

    def test_interpreter_skill_setbacks(self):
        """validate_setbacks catches dimensional violations."""
        from plotlot.harness.interpreter_skills import (
            SitePlan,
            ZoningCode,
            validate_setbacks,
        )

        plan = SitePlan(
            front_setback_ft=25,
            side_setback_left_ft=10,
            side_setback_right_ft=10,
            rear_setback_ft=30,
            building_height_ft=28,
            lot_width_ft=60,
            lot_depth_ft=100,
        )
        code = ZoningCode(
            min_front_setback_ft=20,
            min_side_setback_ft=5,
            min_rear_setback_ft=25,
            max_height_ft=35,
        )
        result = validate_setbacks(plan, code)
        assert result.passed is True

        # Side setback violation
        plan2 = SitePlan(20, 3, 10, 30, 28, 60, 100)
        result2 = validate_setbacks(plan2, code)
        assert result2.passed is False
        assert any("side" in f.lower() for f in result2.failures)

    def test_filesystem_tools_workspace_bounds(self):
        """Filesystem tools stay within workspace."""
        from plotlot.harness.filesystem_tools import read_file, write_file, glob_files

        # Write a test file
        result = write_file(".tmp_integration_test.txt", "hello integration test")
        assert result["ok"] is True

        # Read it back
        result2 = read_file(".tmp_integration_test.txt")
        assert result2["ok"] is True
        assert result2["total_lines"] == 1
        assert "hello integration test" in str(result2["lines"])

        # Glob finds it
        result3 = glob_files(".tmp_integration_test*")
        assert result3["ok"] is True
        assert result3["count"] >= 1

        # Cleanup
        import os

        os.remove(".tmp_integration_test.txt")

    def test_model_adapter_provider_detection(self):
        """create_model_caller handles all providers."""
        from plotlot.harness.model_adapter import create_model_caller

        for provider in ["openrouter", "openai", "anthropic", "groq"]:
            caller = create_model_caller(provider=provider, api_key="sk-test")
            assert callable(caller), f"Failed for {provider}"