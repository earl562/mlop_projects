"""Harness execution API.

This endpoint is the first workspace-native seam: it runs a named skill (or
routes a prompt to a skill) through the internal HarnessRuntime.
"""

from __future__ import annotations

from fastapi import APIRouter

from plotlot.api.schemas_workspace import HarnessRunRequest
from plotlot.harness.contracts import HarnessContext, SkillInput
from plotlot.harness.bootstrap import build_default_runtime

router = APIRouter(prefix="/api/v1/harness", tags=["harness"])


@router.post("/run")
async def run_harness(req: HarnessRunRequest) -> dict:
    runtime = build_default_runtime()

    skill_name = req.skill or req.intent or runtime.router.route(req.prompt)
    skill_input = SkillInput(
        prompt=req.prompt,
        payload=req.payload,
        context=HarnessContext(
            workspace_id=req.workspace_id,
            project_id=req.project_id,
            site_id=req.site_id,
        ),
    )

    if req.skill:
        output = await runtime.run_skill(req.skill, skill_input)
    elif req.intent:
        output = await runtime.route_and_run(req.intent, skill_input)
    else:
        output = await runtime.run(skill_input, skill_name=skill_name)
    return {
        "status": output.status,
        "summary": output.summary,
        "data": output.data,
        "evidence_ids": output.evidence_ids,
        "open_questions": output.open_questions,
        "next_actions": output.next_actions,
    }
