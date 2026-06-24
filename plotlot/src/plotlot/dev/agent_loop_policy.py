from __future__ import annotations

from typing import Final

from plotlot.dev.agent_loop_models import AgentWorkerPolicy, Phase

DEFAULT_WORKER_MODEL: Final = "deepseek-v4-flash"
COMPLEX_REVIEW_MODEL: Final = "gpt-5.5"

_PHASE_POLICIES: Final[dict[Phase, AgentWorkerPolicy]] = {
    Phase.PLAN: AgentWorkerPolicy(
        phase=Phase.PLAN,
        worker="planning-agent",
        primary_model=DEFAULT_WORKER_MODEL,
        escalation_model=COMPLEX_REVIEW_MODEL,
        purpose="Scope work, inspect git state, and choose the next atomic slice.",
        gpt_55_allowed=True,
    ),
    Phase.DEBUG: AgentWorkerPolicy(
        phase=Phase.DEBUG,
        worker="debugging-agent",
        primary_model=DEFAULT_WORKER_MODEL,
        escalation_model=None,
        purpose="Collect local runtime, dependency, and authentication readiness signals.",
        gpt_55_allowed=False,
    ),
    Phase.HYGIENE: AgentWorkerPolicy(
        phase=Phase.HYGIENE,
        worker="hygiene-agent",
        primary_model=DEFAULT_WORKER_MODEL,
        escalation_model=None,
        purpose="Run repository hygiene and CI policy checks before deeper tests.",
        gpt_55_allowed=False,
    ),
    Phase.BACKEND: AgentWorkerPolicy(
        phase=Phase.BACKEND,
        worker="backend-testing-agent",
        primary_model=DEFAULT_WORKER_MODEL,
        escalation_model=None,
        purpose="Run backend lint, type, and unit-test gates.",
        gpt_55_allowed=False,
    ),
    Phase.EVAL: AgentWorkerPolicy(
        phase=Phase.EVAL,
        worker="eval-agent",
        primary_model=DEFAULT_WORKER_MODEL,
        escalation_model=None,
        purpose="Run lookup, evidence, and agentic harness eval gates.",
        gpt_55_allowed=False,
    ),
    Phase.FRONTEND: AgentWorkerPolicy(
        phase=Phase.FRONTEND,
        worker="frontend-testing-agent",
        primary_model=DEFAULT_WORKER_MODEL,
        escalation_model=None,
        purpose="Run frontend lint, typecheck, component tests, and build.",
        gpt_55_allowed=False,
    ),
    Phase.BROWSER: AgentWorkerPolicy(
        phase=Phase.BROWSER,
        worker="browser-qa-agent",
        primary_model=DEFAULT_WORKER_MODEL,
        escalation_model=None,
        purpose="Run Playwright browser checks and capture UI regressions.",
        gpt_55_allowed=False,
    ),
    Phase.REVIEW: AgentWorkerPolicy(
        phase=Phase.REVIEW,
        worker="review-agent",
        primary_model=COMPLEX_REVIEW_MODEL,
        escalation_model=None,
        purpose="Review complex diffs, release risk, evidence gaps, and regression signals.",
        gpt_55_allowed=True,
    ),
    Phase.DEPLOY_READINESS: AgentWorkerPolicy(
        phase=Phase.DEPLOY_READINESS,
        worker="deployment-agent",
        primary_model=DEFAULT_WORKER_MODEL,
        escalation_model=COMPLEX_REVIEW_MODEL,
        purpose="Check GitHub/auth/PR readiness and escalate only on release blockers.",
        gpt_55_allowed=True,
    ),
}


def agent_worker_policies(phases: tuple[Phase, ...]) -> tuple[AgentWorkerPolicy, ...]:
    return tuple(_PHASE_POLICIES[phase] for phase in phases)
