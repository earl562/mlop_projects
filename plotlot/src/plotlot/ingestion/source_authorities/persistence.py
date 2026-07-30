"""Source authority persistence — upsert + list (review feedback #14).

Previously seed_south_florida_authorities only returned in-memory objects.
This service persists them to jurisdiction_source_authorities.
"""

from __future__ import annotations

from sqlalchemy import select

from plotlot.ingestion.source_authorities.models import JurisdictionSourceAuthority
from plotlot.storage.db import get_session
from plotlot.storage.models import JurisdictionSourceAuthorityORM


async def upsert_source_authority(
    authority: JurisdictionSourceAuthority,
) -> JurisdictionSourceAuthorityORM:
    session = await get_session()
    try:
        existing = (
            await session.execute(
                select(JurisdictionSourceAuthorityORM).where(
                    JurisdictionSourceAuthorityORM.state == authority.state,
                    JurisdictionSourceAuthorityORM.county == authority.county,
                    JurisdictionSourceAuthorityORM.municipality == authority.municipality,
                    JurisdictionSourceAuthorityORM.authority_scope
                    == authority.authority_scope.value,
                    JurisdictionSourceAuthorityORM.provider == authority.provider.value,
                )
            )
        ).scalar_one_or_none()
        if existing:
            existing.source_url = authority.source_url
            existing.source_title = authority.source_title
            existing.canonical_url = authority.canonical_url
            existing.official_status = authority.official_status_value
            existing.legal_caveat = authority.legal_caveat
            existing.metadata_json = authority.metadata_json
            orm = existing
        else:
            orm = JurisdictionSourceAuthorityORM(
                id=authority.id,
                state=authority.state,
                county=authority.county,
                municipality=authority.municipality,
                jurisdiction_type=authority.jurisdiction_type_value,
                authority_scope=authority.authority_scope_value,
                provider=authority.provider_value,
                canonical_url=authority.canonical_url,
                source_url=authority.source_url,
                source_title=authority.source_title,
                official_status=authority.official_status_value,
                legal_caveat=authority.legal_caveat,
                metadata_json=authority.metadata_json,
            )
            session.add(orm)
        await session.commit()
        return orm
    finally:
        await session.close()


async def list_source_authorities(
    *,
    state: str | None = None,
    authority_scope: str | None = None,
) -> list[JurisdictionSourceAuthorityORM]:
    session = await get_session()
    try:
        stmt = select(JurisdictionSourceAuthorityORM)
        if state:
            stmt = stmt.where(JurisdictionSourceAuthorityORM.state == state)
        if authority_scope:
            stmt = stmt.where(JurisdictionSourceAuthorityORM.authority_scope == authority_scope)
        result = await session.execute(
            stmt.order_by(
                JurisdictionSourceAuthorityORM.county, JurisdictionSourceAuthorityORM.municipality
            )
        )
        return list(result.scalars().all())
    finally:
        await session.close()


async def seed_and_persist_south_florida_authorities() -> int:
    """Seed + persist; returns count."""
    from plotlot.ingestion.source_authorities.south_florida import seed_south_florida_authorities

    auths = seed_south_florida_authorities()
    n = 0
    for a in auths:
        await upsert_source_authority(a)
        n += 1
    return n


__all__ = [
    "list_source_authorities",
    "seed_and_persist_south_florida_authorities",
    "upsert_source_authority",
]
