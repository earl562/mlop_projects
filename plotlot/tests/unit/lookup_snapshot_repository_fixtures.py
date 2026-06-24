from __future__ import annotations

from typing import TypeVar

from plotlot.core.types import DensityAnalysis, PropertyRecord, SourceRef, ZoningReport

T = TypeVar("T")


class FakePersistenceSession:
    def __init__(self) -> None:
        self.rows: dict[tuple[type, str], T] = {}
        self.added: list[T] = []
        self.flushed = 0
        self.committed = 0

    async def get(self, model: type[T], key: str) -> T | None:
        row = self.rows.get((model, key))
        if isinstance(row, model):
            return row
        return None

    def add(self, row: T) -> None:
        self.added.append(row)
        self.rows[(type(row), row.id)] = row

    async def flush(self) -> None:
        self.flushed += 1

    async def commit(self) -> None:
        self.committed += 1


def report(
    *,
    with_ordinance: bool = True,
    source_urls: tuple[str, ...] = (),
    with_density_analysis: bool = False,
) -> ZoningReport:
    return ZoningReport(
        address="7940 Plantation Blvd, Miramar, FL 33023",
        formatted_address="7940 Plantation Blvd, Miramar, FL 33023",
        municipality="Miramar",
        county="Broward",
        zoning_district="RS-4",
        max_height="35 ft",
        parking_requirements="2 spaces per unit",
        property_record=PropertyRecord(
            folio="504210230010",
            address="7940 PLANTATION BLVD",
            municipality="Miramar",
            county="Broward",
            zoning_code="RS-4",
            lot_size_sqft=8000.0,
        ),
        source_refs=(
            [
                SourceRef(
                    section="Sec. 500",
                    section_title="Dimensional Standards",
                    chunk_text_preview="RS-4 height and parking standards.",
                    score=0.91,
                )
            ]
            if with_ordinance
            else []
        ),
        sources=list(source_urls),
        density_analysis=(
            DensityAnalysis(
                max_units=2,
                governing_constraint="density",
                constraints=[],
                lot_size_sqft=8000.0,
                notes=["Density limited to two units."],
            )
            if with_density_analysis
            else None
        ),
        confidence="medium",
    )
