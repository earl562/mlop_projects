"""Phase 1 TDD: source authority + snapshot + event models (failing first).

Master spec §7 (DB plan), §5 (ingestion spec), §6 (events spec).
Tests written BEFORE implementation — they fail until the models + migration land.
"""

from __future__ import annotations

import pytest

# These imports fail until the models exist (the point of TDD).
from plotlot.ingestion.source_authorities.models import (
    AuthorityScope,
    JurisdictionSourceAuthority,
    JurisdictionType,
    OfficialStatus,
    Provider,
)
from plotlot.ingestion.snapshots import OrdinanceSourceSnapshot
from plotlot.ingestion.events import HarnessEvent, IngestionEventType


class TestSourceAuthorityEnums:
    """Master spec §5: provider + jurisdiction + scope enums."""

    def test_provider_enum_covers_all_codifiers(self):
        # Master spec §5 provider list + §9 provider-agnostic rule.
        for p in (
            "official_html",
            "official_pdf",
            "municode",
            "ecode360",
            "amlegal",
            "codepublishing",
            "municipal_codes",
            "encodeplus",
            "arcgis",
            "manual",
        ):
            assert Provider(p)  # all valid

    def test_jurisdiction_type_enum(self):
        for t in ("county", "municipality", "special_district"):
            assert JurisdictionType(t)

    def test_authority_scope_enum(self):
        for s in (
            "zoning",
            "land_development",
            "code_of_ordinances",
            "gis_zoning",
            "overlays",
            "comp_plan",
            "adopted_ordinances",
        ):
            assert AuthorityScope(s)

    def test_official_status_enum(self):
        for s in ("official", "publisher_copy", "informational", "unknown"):
            assert OfficialStatus(s)


class TestSourceAuthorityModel:
    """Master spec §5: JurisdictionSourceAuthority fields + invariants."""

    def test_minimal_authority(self):
        a = JurisdictionSourceAuthority(
            state="FL",
            county="Miami-Dade",
            municipality="Miami",
            jurisdiction_type=JurisdictionType.MUNICIPALITY,
            authority_scope=AuthorityScope.ZONING,
            provider=Provider.MUNICODE,
            canonical_url="https://library.municode.com/fl/miami",
            source_url="https://library.municode.com/fl/miami",
            source_title="City of Miami Code",
            official_status=OfficialStatus.PUBLISHER_COPY,
            legal_caveat="Online code may not be the official/current copy.",
        )
        assert a.state == "FL"
        assert a.jurisdiction_type is JurisdictionType.MUNICIPALITY
        assert a.freshness_policy  # has a default

    def test_rejects_empty_source_url(self):
        with pytest.raises((ValueError, Exception)):
            JurisdictionSourceAuthority(
                state="FL",
                county="Broward",
                municipality="Davie",
                jurisdiction_type=JurisdictionType.MUNICIPALITY,
                authority_scope=AuthorityScope.ZONING,
                provider=Provider.MUNICODE,
                canonical_url="",  # empty — must reject
                source_url="",
                source_title="",
                official_status=OfficialStatus.UNKNOWN,
                legal_caveat="",
            )

    def test_south_fl_county_normalization(self):
        # Miami-Dade unincorporated is a separate authority (spec §5 special handling).
        a = JurisdictionSourceAuthority(
            state="FL",
            county="Miami-Dade",
            municipality=None,  # unincorporated
            jurisdiction_type=JurisdictionType.COUNTY,
            authority_scope=AuthorityScope.ZONING,
            provider=Provider.MUNICODE,
            canonical_url="https://library.municode.com/fl/miami_dade",
            source_url="https://library.municode.com/fl/miami_dade",
            source_title="Miami-Dade County Code",
            official_status=OfficialStatus.PUBLISHER_COPY,
            legal_caveat="verify with municipality",
        )
        assert a.jurisdiction_type is JurisdictionType.COUNTY
        assert a.municipality is None


class TestSourceSnapshotModel:
    """Master spec §7: snapshot content hashing + natural key."""

    def test_content_hash_is_deterministic(self):
        s1 = OrdinanceSourceSnapshot(
            source_authority_id="auth_1",
            source_url="https://x",
            content="<html>same</html>",
        )
        s2 = OrdinanceSourceSnapshot(
            source_authority_id="auth_1",
            source_url="https://x",
            content="<html>same</html>",
        )
        assert s1.content_hash == s2.content_hash
        assert s1.content_hash  # non-empty

    def test_different_content_different_hash(self):
        s1 = OrdinanceSourceSnapshot(
            source_authority_id="auth_1", source_url="https://x", content="A"
        )
        s2 = OrdinanceSourceSnapshot(
            source_authority_id="auth_1", source_url="https://x", content="B"
        )
        assert s1.content_hash != s2.content_hash


class TestHarnessEventModel:
    """Master spec §6: event envelope + invariants."""

    def test_event_envelope_required_fields(self):
        e = HarnessEvent(
            type=IngestionEventType.SOURCE_FETCH_COMPLETED,
            severity="info",
            payload={
                "authority_id": "auth_1",
                "snapshot_id": "snap_1",
                "http_status": 200,
                "content_hash": "abc",
                "bytes": 1234,
            },
        )
        assert e.id  # auto-generated
        assert e.timestamp
        assert e.correlation_id
        assert e.type == IngestionEventType.SOURCE_FETCH_COMPLETED.value

    def test_unknown_event_type_rejected(self):
        with pytest.raises((ValueError, Exception)):
            HarnessEvent(type="totally_made_up_event", severity="info", payload={})

    def test_required_payload_fields_enforced(self):
        # source_fetch_completed requires authority_id, snapshot_id, http_status,
        # content_hash, bytes (per events spec §2).
        with pytest.raises((ValueError, Exception)):
            HarnessEvent(
                type=IngestionEventType.SOURCE_FETCH_COMPLETED,
                severity="info",
                payload={"authority_id": "auth_1"},  # missing fields
            )
