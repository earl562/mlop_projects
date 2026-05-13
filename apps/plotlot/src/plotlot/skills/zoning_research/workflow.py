"""Skill wrapper around the existing zoning lookup pipeline."""

from __future__ import annotations

from typing import TYPE_CHECKING

from plotlot.harness.contracts import SkillInput, SkillOutput
from plotlot.pipeline.lookup import lookup_address, report_to_dict

if TYPE_CHECKING:  # pragma: no cover
    from plotlot.harness.runtime import HarnessRuntime


class ZoningResearchSkill:
    """Repo-owned skill that preserves the current lookup pipeline contract."""

    name: str = "zoning_research"
    triggers: tuple[str, ...] = (
        "zoning",
        "setback",
        "density",
        "allowed use",
        "max units",
        "parcel",
        "site feasibility",
        "build",
    )

    async def run(self, runtime: "HarnessRuntime", skill_input: SkillInput) -> SkillOutput:
        address = skill_input.payload.get("address") or skill_input.prompt
        if not address:
            return SkillOutput(
                status="needs_input",
                summary="Zoning research requires a property address.",
                open_questions=["Which address or parcel should be analyzed?"],
            )

        report = await lookup_address(str(address))
        if report is None:
            return SkillOutput(
                status="error",
                summary="The zoning lookup pipeline did not return a report.",
                open_questions=["Confirm the address and jurisdiction."],
            )

        report_data = report_to_dict(report)
        evidence_sources = [
            {
                "source_type": "ordinance_or_public_record",
                "source_title": source,
                "tool_name": "zoning_research",
                "confidence": report.confidence or "medium",
            }
            for source in report.sources
        ]
        if report.source_refs:
            evidence_sources.extend(
                {
                    "source_type": "ordinance_chunk",
                    "source_title": ref.section_title or ref.section,
                    "value": {
                        "section": ref.section,
                        "preview": ref.chunk_text_preview,
                        "score": ref.score,
                    },
                    "tool_name": "search_ordinance",
                    "confidence": "medium",
                }
                for ref in report.source_refs
            )

        evidence_ids: list[str] = []
        if runtime.evidence is not None:
            evidence_ids = await runtime.evidence.record_zoning_report(
                workspace_id=skill_input.context.workspace_id,
                project_id=skill_input.context.project_id,
                site_id=skill_input.context.site_id,
                report=report,
            )

        return SkillOutput(
            status="success",
            summary=report.summary or f"Completed zoning research for {report.formatted_address}.",
            data={
                "report": report_data,
                "evidence_candidates": evidence_sources,
            },
            evidence_ids=evidence_ids,
            open_questions=[]
            if report.confidence != "low"
            else ["Low-confidence zoning output needs review."],
            next_actions=["review_evidence", "generate_report", "run_site_feasibility"],
        )
