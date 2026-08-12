"""Prose extraction of dimensional standards from PDF-scraped codes.

Every fixture here is VERBATIM San Diego Municipal Code text as it actually sits
in `ordinance_chunks` — including the line wrapping and the PDF page furniture
that the scraper leaves behind. San Diego has 2,910 chunks and zero pipe
characters, so the markdown-table extractor cannot read a single one of them.
"""

from __future__ import annotations

from plotlot.domain.dimensional_standard import (
    VerificationStatus,
    extract_dimensional_standards_from_prose,
)

_KW = dict(
    municipality="San Diego",
    county="San Diego",
    state="CA",
    source_section_id="Art.01 Div.04",
)


def _codes(rows):
    return {r.district_code: r.min_lot_area_sqft for r in rows}


# Verbatim from chunk id=40306.
_RM_BLOCK = """(2) The following zones permit medium density multiple dwelling units:
• RM-2-4 permits a maximum density of 1 dwelling unit for each
1,750 square feet of lot area
• RM-2-5 permits a maximum density of 1 dwelling unit for each
1,500 square feet of lot area
(3) The following zones permit medium density multiple dwelling units
with limited commercial uses:
• RM-3-7 permits a maximum density of 1 dwelling unit for each
1,000 square feet of lot area
• RM-3-8 permits a maximum density of 1 dwelling unit for each
800 square feet of lot area
(4) The following zones permit urbanized, high density multiple dwelling
units with limited commercial uses:
• RM-4-10 permits a maximum density of 1 dwelling unit for
each 400 square feet of lot area
"""

# Verbatim from chunk id=40305 — note the RT list uses a different verb.
_RT_BLOCK = """(b) The RT zones are differentiated based on the minimum lot size as follows:
• RT-1-1 requires minimum 3,500-square-foot lots
• RT-1-2 requires minimum 3,000-square-foot lots
• RT-1-5 requires minimum 1,600-square-foot lots
"""


def test_extracts_rm_densities_across_wrapped_lines():
    """The number lives on the NEXT line — 'for each\\n1,000 square feet'."""
    got = _codes(extract_dimensional_standards_from_prose(_RM_BLOCK, **_KW))
    assert got == {
        "RM-2-4": 1750.0,
        "RM-2-5": 1500.0,
        "RM-3-7": 1000.0,
        "RM-3-8": 800.0,
        "RM-4-10": 400.0,
    }


def test_the_canonical_parcels_district_is_exactly_1000():
    """1233 Hueneme is RM-3-7; 7,710 sqft / 1,000 = 7 units. This single value is
    what the whole canonical regression case rests on."""
    rows = extract_dimensional_standards_from_prose(_RM_BLOCK, **_KW)
    rm37 = next(r for r in rows if r.district_code == "RM-3-7")
    assert rm37.min_lot_area_sqft == 1000.0
    # Exact integer arithmetic through the calculator's accessor — no float drift.
    assert rm37.to_numeric_zoning_params().min_lot_area_per_unit_sqft == 1000.0


def test_extracts_rt_minimum_lot_sizes():
    got = _codes(extract_dimensional_standards_from_prose(_RT_BLOCK, **_KW))
    assert got == {"RT-1-1": 3500.0, "RT-1-2": 3000.0, "RT-1-5": 1600.0}


def test_page_furniture_between_phrase_and_number_is_refused_not_misread():
    """THE failure that matters.

    The scraper injects a running header mid-sentence. Binding '13' or '2026'
    from that header as a per-unit lot area would be a confidently wrong
    deterministic answer — far worse than the LLM flakiness this replaces. The
    match must simply fail; the same sentence appears cleanly in the overlapping
    neighbour chunk."""
    corrupted = (
        "• RM-1-3 permits a maximum density of 1 dwelling unit for each\n"
        "Ch. Art. Div.\n13 1 4 4\n"
        "San Diego Municipal Code Chapter 13: Zones\n(3-2026)\n"
        "2,000 square feet of lot area\n"
    )
    assert extract_dimensional_standards_from_prose(corrupted, **_KW) == []


def test_a_sentence_truncated_at_a_chunk_boundary_yields_nothing():
    """Chunk 40305 ends mid-sentence. It must not reach into whatever follows."""
    truncated = "• RM-1-3 permits a maximum density of 1 dwelling unit for each"
    assert extract_dimensional_standards_from_prose(truncated, **_KW) == []


def test_a_truncated_statement_cannot_borrow_the_next_districts_number():
    """Two bullets, the first cut off. The bounded, bullet-excluding gap stops the
    first district from binding the second's value."""
    text = (
        "• RM-1-3 permits a maximum density of 1 dwelling unit for each\n"
        "• RM-2-4 permits a maximum density of 1 dwelling unit for each\n"
        "1,750 square feet of lot area\n"
    )
    got = _codes(extract_dimensional_standards_from_prose(text, **_KW))
    assert got == {"RM-2-4": 1750.0}
    assert "RM-1-3" not in got


def test_conflicting_values_for_one_district_in_one_chunk_are_dropped():
    text = (
        "• RM-3-7 permits a maximum density of 1 dwelling unit for each "
        "1,000 square feet of lot area\n"
        "• RM-3-7 permits a maximum density of 1 dwelling unit for each "
        "600 square feet of lot area\n"
    )
    assert extract_dimensional_standards_from_prose(text, **_KW) == []


def test_implausible_values_are_rejected():
    """A misparse should be dropped, not stored as a standard."""
    text = (
        "• RM-9-9 permits a maximum density of 1 dwelling unit for each "
        "12 square feet of lot area\n"
    )
    assert extract_dimensional_standards_from_prose(text, **_KW) == []


def test_prose_without_any_district_statement_yields_nothing():
    text = (
        "(a) The purpose of the RM zones is to provide for multiple dwelling unit "
        "development at varying densities."
    )
    assert extract_dimensional_standards_from_prose(text, **_KW) == []


def test_rows_carry_provenance_and_default_to_unverified():
    rows = extract_dimensional_standards_from_prose(_RM_BLOCK, **_KW, source_url="http://x")
    r = rows[0]
    assert r.source_section_id == "Art.01 Div.04"
    assert r.source_url == "http://x"
    assert r.verification_status is VerificationStatus.UNVERIFIED
    assert r.is_verified_fact_source() is False
