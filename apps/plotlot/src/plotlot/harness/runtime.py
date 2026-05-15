"""Minimal harness runtime for skill execution."""

from __future__ import annotations

from plotlot.harness.connector_gateway import ConnectorGateway
from plotlot.harness.context_broker import ContextBroker
from plotlot.harness.contracts import SkillInput, SkillOutput
from plotlot.harness.evidence import EvidenceRecorder
from plotlot.harness.model_gateway import ModelGateway
from plotlot.harness.router import IntentRouter
from plotlot.harness.sandbox import SandboxRunner
from plotlot.harness.skill_registry import SkillRegistry


class HarnessRuntime:
    """Routes prompts to registered skills and executes them."""

    def __init__(
        self,
        *,
        registry: SkillRegistry | None = None,
        context_broker: ContextBroker | None = None,
        evidence_recorder: EvidenceRecorder | None = None,
        intent_router: IntentRouter | None = None,
        model_gateway: ModelGateway | None = None,
        connector_gateway: ConnectorGateway | None = None,
        sandbox_runner: SandboxRunner | None = None,
        policy_engine: object | None = None,
    ) -> None:
        self.registry = registry or SkillRegistry()
        self.context_broker = context_broker or ContextBroker()
        self.evidence = evidence_recorder
        self.router = intent_router or IntentRouter()
        self.model_gateway = model_gateway
        self.connector_gateway = connector_gateway
        self.sandbox = sandbox_runner
        self.policy = policy_engine

    async def run_skill(self, skill_name: str, skill_input: SkillInput) -> SkillOutput:
        skill = self.registry.get(skill_name)
        if skill is None:
            return SkillOutput(
                status="no_skill",
                summary=f"No skill named '{skill_name}' is registered.",
                open_questions=["Choose a skill or provide a more specific land-use task."],
            )
        return await skill.run(self, skill_input)

    async def route_and_run(self, intent: str, skill_input: SkillInput) -> SkillOutput:
        skill = self.registry.match(intent)
        if skill is not None:
            return await skill.run(self, skill_input)
        return await self.run_skill(self.router.route(skill_input.prompt), skill_input)

    async def run(self, skill_input: SkillInput, skill_name: str | None = None) -> SkillOutput:
        if skill_name:
            return await self.run_skill(skill_name, skill_input)

        routed = self.registry.route(skill_input.prompt)
        if routed is not None:
            return await routed.run(self, skill_input)

        return await self.run_skill(self.router.route(skill_input.prompt), skill_input)
