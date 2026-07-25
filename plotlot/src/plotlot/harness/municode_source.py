from __future__ import annotations

from dataclasses import dataclass

from pydantic import Field

from plotlot.harness.contracts import (
    ApplicabilityStatus,
    ApplicabilityScope,
    CountyName,
    EvidenceId,
    EvidenceItem,
    EvidenceSourceType,
    FreshnessStatus,
    JsonObject,
    RunId,
    SourceCatalogEntry,
    SourceLane,
    SourceMode,
)
from plotlot.harness.contracts.base import HarnessContract


@dataclass(frozen=True, slots=True)
class MunicodeSectionNotFoundError(Exception):
    section_id: str

    def __str__(self) -> str:
        return f"Municode fixture section not found: {self.section_id}"


@dataclass(frozen=True, slots=True)
class MunicodeModeUnsupportedError(Exception):
    source_mode: SourceMode

    def __str__(self) -> str:
        return f"Municode {self.source_mode.value} mode is not wired in the harness yet"


class MunicodeSection(HarnessContract):
    section_id: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    county: CountyName
    municipality: str = Field(min_length=1)
    provider: str = "municode"
    code_title: str = Field(min_length=1)
    section_title: str = Field(min_length=1)
    section_identifier: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    raw_excerpt: str = Field(min_length=1)
    normalized_text: str = Field(min_length=1)
    content_hash: str = Field(min_length=1)
    freshness_status: FreshnessStatus
    official_verification_note: str = Field(min_length=1)
    source_mode: SourceMode
    metadata: JsonObject = Field(default_factory=dict)


class MunicodeSearchResult(HarnessContract):
    section_id: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    municipality: str = Field(min_length=1)
    provider: str = "municode"
    section_title: str = Field(min_length=1)
    section_identifier: str = Field(min_length=1)
    source_url: str = Field(min_length=1)
    snippet: str = Field(min_length=1)
    freshness_status: FreshnessStatus
    official_verification_note: str = Field(min_length=1)
    score: float = Field(ge=0, le=1)


class OrdinanceRuleExtraction(HarnessContract):
    source_section_id: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    rules: JsonObject
    requires_official_verification: bool
    caveats: list[str]


def search_municode(
    *,
    jurisdiction: str,
    query: str,
    source_mode: SourceMode,
) -> list[MunicodeSearchResult]:
    _require_fixture(source_mode)
    query_text = query.casefold()
    jurisdiction_text = jurisdiction.casefold()
    return [
        _search_result(section)
        for section in _fixture_sections()
        if _matches_search(section, jurisdiction=jurisdiction_text, query=query_text)
    ]


def load_municode_source_catalog(source_mode: SourceMode) -> list[SourceCatalogEntry]:
    _require_fixture(source_mode)
    return [
        SourceCatalogEntry(
            source_id=f"src_{section.section_id}",
            lane=SourceLane.ORDINANCE_CODE,
            provider=section.provider,
            source_type="municode_section",
            jurisdiction=section.jurisdiction,
            county=section.county,
            municipality=section.municipality,
            dataset_name=section.code_title,
            layer_name=section.section_title,
            source_url=section.source_url,
            code_url=section.source_url,
            freshness_policy="requires_official_verification",
            applicability_scope=ApplicabilityScope.MUNICIPAL,
            access_status="public",
            metadata={
                "section_id": section.section_id,
                "section_identifier": section.section_identifier,
                "official_verification_note": section.official_verification_note,
            },
        )
        for section in _fixture_sections()
    ]


def get_municode_section(section_id: str, *, source_mode: SourceMode) -> MunicodeSection:
    _require_fixture(source_mode)
    for section in _fixture_sections():
        if section.section_id == section_id:
            return section
    raise MunicodeSectionNotFoundError(section_id=section_id)


def extract_ordinance_rules(section: MunicodeSection) -> OrdinanceRuleExtraction:
    rules: JsonObject = {}
    if "1.5 parking spaces" in section.normalized_text:
        rules["parking_spaces_per_dwelling_unit"] = 1.5
    if "t4-r" in section.normalized_text.casefold():
        rules["zoning_district"] = "T4-R"
    return OrdinanceRuleExtraction(
        source_section_id=section.section_id,
        jurisdiction=section.jurisdiction,
        rules=rules,
        requires_official_verification=True,
        caveats=[
            "Municode fixture evidence is preliminary and requires official municipal verification."
        ],
    )


def create_municode_evidence(section: MunicodeSection, *, run_id: str) -> EvidenceItem:
    return EvidenceItem(
        evidence_id=EvidenceId(f"ev_{run_id}_{section.section_id}"),
        run_id=RunId(run_id),
        source_type=EvidenceSourceType.MUNICODE_SECTION,
        source_name=f"{section.jurisdiction} {section.section_identifier}",
        source_url=section.source_url,
        source_identifier=section.section_id,
        provider=section.provider,
        jurisdiction=section.jurisdiction,
        county=section.county,
        municipality=section.municipality,
        freshness_status=section.freshness_status,
        applicability=ApplicabilityStatus.REQUIRES_MUNICIPAL_VERIFICATION,
        raw_excerpt=section.raw_excerpt,
        normalized_text=section.normalized_text,
        structured_payload={
            "code_title": section.code_title,
            "section_title": section.section_title,
            "section_identifier": section.section_identifier,
            "content_hash": section.content_hash,
        },
        confidence=0.72,
        source_mode=section.source_mode,
        metadata={
            "provider": section.provider,
            "official_verification_note": section.official_verification_note,
        },
    )


def _require_fixture(source_mode: SourceMode) -> None:
    if source_mode != SourceMode.FIXTURE:
        raise MunicodeModeUnsupportedError(source_mode=source_mode)


def _matches_search(section: MunicodeSection, *, jurisdiction: str, query: str) -> bool:
    haystack = (
        f"{section.jurisdiction} {section.municipality} {section.section_title} "
        f"{section.section_identifier} {section.normalized_text}"
    ).casefold()
    return jurisdiction in haystack and query in haystack


def _search_result(section: MunicodeSection) -> MunicodeSearchResult:
    return MunicodeSearchResult(
        section_id=section.section_id,
        jurisdiction=section.jurisdiction,
        municipality=section.municipality,
        section_title=section.section_title,
        section_identifier=section.section_identifier,
        source_url=section.source_url,
        snippet=section.raw_excerpt[:240],
        freshness_status=section.freshness_status,
        official_verification_note=section.official_verification_note,
        score=0.92,
    )


def _fixture_sections() -> list[MunicodeSection]:
    note = "Online Municode text may not be the official current copy; official municipal verification is required before closing."
    return [
        MunicodeSection(
            section_id="municode_miami_parking_fixture",
            jurisdiction="City of Miami",
            county=CountyName("Miami-Dade"),
            municipality="Miami",
            code_title="Miami 21 Zoning Code",
            section_title="Parking requirements for residential uses",
            section_identifier="Sec. 7.1.2.3",
            source_url="https://library.municode.com/fl/miami/codes/miami_21",
            raw_excerpt="Residential uses in the T4-R district require 1.5 parking spaces per dwelling unit unless an adopted exception applies.",
            normalized_text="Residential uses in the T4-R district require 1.5 parking spaces per dwelling unit unless an adopted exception applies.",
            content_hash="fixture_miami_parking_v1",
            freshness_status=FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
            official_verification_note=note,
            source_mode=SourceMode.FIXTURE,
            metadata={"fixture": True, "topic": "parking"},
        ),
        MunicodeSection(
            section_id="municode_broward_bmsd_zoning_fixture",
            jurisdiction="Broward County",
            county=CountyName("Broward"),
            municipality="BMSD",
            code_title="Broward County Code of Ordinances",
            section_title="BMSD residential zoning district standards",
            section_identifier="Sec. 39-275",
            source_url="https://library.municode.com/fl/broward_county/codes/code_of_ordinances",
            raw_excerpt="BMSD residential zoning standards apply only to unincorporated Broward or BMSD areas unless municipal law incorporates them.",
            normalized_text="BMSD residential zoning standards apply only to unincorporated Broward or BMSD areas unless municipal law incorporates them.",
            content_hash="fixture_broward_bmsd_zoning_v1",
            freshness_status=FreshnessStatus.REQUIRES_OFFICIAL_VERIFICATION,
            official_verification_note=note,
            source_mode=SourceMode.FIXTURE,
            metadata={"fixture": True, "topic": "zoning"},
        ),
    ]
