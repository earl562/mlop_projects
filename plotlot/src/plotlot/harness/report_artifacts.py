from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from plotlot.land_use.models import EvidenceBackedReportSection, ReportClaim, ToolContext


class DocumentAssumption(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    text: str = Field(min_length=1)


class DocumentClaimInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    key: str = Field(min_length=1)
    text: str = Field(min_length=1)
    material: bool = True
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("evidence_ids")
    @classmethod
    def _strip_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(evidence_id.strip() for evidence_id in value if evidence_id.strip())


class DocumentSectionInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    claims: tuple[DocumentClaimInput, ...] = Field(min_length=1)
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)

    @field_validator("evidence_ids")
    @classmethod
    def _strip_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(evidence_id.strip() for evidence_id in value if evidence_id.strip())


class GenerateDocumentArgs(BaseModel):
    model_config = ConfigDict(frozen=True)

    title: str = Field(default="Evidence-backed report", min_length=1)
    evidence_ids: tuple[str, ...] = Field(default_factory=tuple)
    sections: tuple[DocumentSectionInput, ...] = Field(default_factory=tuple)
    assumptions: tuple[DocumentAssumption, ...] = Field(default_factory=tuple)

    @field_validator("evidence_ids")
    @classmethod
    def _strip_evidence_ids(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return tuple(evidence_id.strip() for evidence_id in value if evidence_id.strip())


async def handle_generate_document(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    try:
        parsed = GenerateDocumentArgs.model_validate(args)
    except ValidationError as exc:
        return {"status": "error", "message": str(exc), "artifacts": {}}

    sections = _report_sections(parsed)
    unsupported_claim_keys = _unsupported_claim_keys(sections)
    if unsupported_claim_keys:
        return {
            "status": "blocked",
            "message": "Material report claims require evidence_ids before document generation.",
            "unsupported_claim_keys": unsupported_claim_keys,
            "assumption_keys": [assumption.key for assumption in parsed.assumptions],
            "artifacts": {},
        }

    evidence_ids = _all_evidence_ids(parsed, sections)
    if not evidence_ids:
        return {
            "status": "error",
            "message": "generate_document requires evidence_ids or evidence-backed sections",
            "artifacts": {},
        }
    missing_evidence_ids = _unrecorded_evidence_ids(evidence_ids, context.recorded_evidence_ids)
    if missing_evidence_ids:
        return {
            "status": "blocked",
            "message": "Report artifacts require recorded evidence items before generation.",
            "missing_evidence_ids": missing_evidence_ids,
            "artifacts": {},
        }

    report_sections = _evidence_backed_sections(sections, evidence_ids)
    report_json = {
        "title": parsed.title.strip(),
        "generated_by": "generate_document",
        "sections": [section.model_dump() for section in report_sections],
        "assumptions": [assumption.model_dump() for assumption in parsed.assumptions],
        "evidence_ids": evidence_ids,
    }

    return {
        "status": "success",
        "evidence_ids": evidence_ids,
        "report": report_json,
        "artifacts": {
            "report": {
                "status": "draft",
                "report_json": report_json,
                "evidence_ids": evidence_ids,
            },
            "document": {
                "document_type": "evidence_report",
                "status": "draft",
                "metadata_json": {
                    "title": parsed.title.strip(),
                    "workspace_id": context.workspace_id,
                    "project_id": context.project_id,
                    "site_id": context.site_id,
                    "evidence_ids": evidence_ids,
                    "assumption_keys": [assumption.key for assumption in parsed.assumptions],
                },
            },
        },
    }


def _report_sections(parsed: GenerateDocumentArgs) -> tuple[DocumentSectionInput, ...]:
    if parsed.sections:
        return parsed.sections

    claims = tuple(
        DocumentClaimInput(
            key=f"evidence.{index}",
            text=f"Supported by evidence item {evidence_id}.",
            evidence_ids=(evidence_id,),
        )
        for index, evidence_id in enumerate(parsed.evidence_ids, start=1)
    )
    return (
        DocumentSectionInput(
            id="sec_evidence",
            title="Evidence",
            claims=claims,
            evidence_ids=parsed.evidence_ids,
        ),
    )


def _unsupported_claim_keys(sections: tuple[DocumentSectionInput, ...]) -> list[str]:
    return [
        claim.key
        for section in sections
        for claim in section.claims
        if claim.material and not claim.evidence_ids
    ]


def _all_evidence_ids(
    parsed: GenerateDocumentArgs, sections: tuple[DocumentSectionInput, ...]
) -> list[str]:
    ordered_ids = list(parsed.evidence_ids)
    for section in sections:
        ordered_ids.extend(section.evidence_ids)
        for claim in section.claims:
            ordered_ids.extend(claim.evidence_ids)
    return list(dict.fromkeys(ordered_ids))


def requested_document_evidence_ids(args: dict[str, Any]) -> tuple[str, ...]:
    try:
        parsed = GenerateDocumentArgs.model_validate(args)
    except ValidationError:
        return ()
    return tuple(_all_evidence_ids(parsed, _report_sections(parsed)))


def _unrecorded_evidence_ids(evidence_ids: list[str], recorded_ids: set[str]) -> list[str]:
    return [evidence_id for evidence_id in evidence_ids if evidence_id not in recorded_ids]


def _evidence_backed_sections(
    sections: tuple[DocumentSectionInput, ...], evidence_ids: list[str]
) -> list[EvidenceBackedReportSection]:
    evidence_id_set = set(evidence_ids)
    return [
        EvidenceBackedReportSection(
            id=section.id,
            title=section.title,
            evidence_ids=sorted(evidence_id_set | set(section.evidence_ids)),
            claims=[
                ReportClaim(
                    key=claim.key,
                    text=claim.text,
                    material=claim.material,
                    evidence_ids=list(claim.evidence_ids),
                )
                for claim in section.claims
            ],
        )
        for section in sections
    ]
