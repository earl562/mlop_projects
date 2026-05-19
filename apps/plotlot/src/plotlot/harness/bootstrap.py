"""Default harness composition."""

from plotlot.harness.connector_gateway import ConnectorGateway
from plotlot.harness.evidence import EvidenceRecorder
from plotlot.harness.model_gateway import NoopModelGateway
from plotlot.harness.runtime import HarnessRuntime
from plotlot.harness.sandbox import LocalNoopSandbox
from plotlot.harness.skill_registry import SkillRegistry
from plotlot.skills.zoning_research import ZoningResearchSkill


def build_default_runtime() -> HarnessRuntime:
    registry = SkillRegistry()
    registry.register(ZoningResearchSkill())
    return HarnessRuntime(
        registry=registry,
        evidence_recorder=EvidenceRecorder(),
        model_gateway=NoopModelGateway(),
        connector_gateway=ConnectorGateway(),
        sandbox_runner=LocalNoopSandbox(),
    )
