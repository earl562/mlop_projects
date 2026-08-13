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


# Verbatim Encinitas and Poway. Both state a minimum lot size AND a worded
# du/acre density in one sentence.
_ENCINITAS = (
    "**R-3: Residential 3** is intended to provide for single-family detached "
    "residential units with minimum lot sizes of 14,500 net square feet and "
    "maximum densities of three units per net acre\n"
    "**R-5: Residential 5** is intended to provide for lower density suburban "
    "development consisting of single-family detached units with minimum lot sizes "
    "of 8,700 net square feet and maximum densities of five units per net acre\n"
)

_POWAY_RS7 = (
    "The RS-7 residential single-family 7 zone is intended as an area for "
    "single-family residential development on minimum lot sizes of 4,500 square "
    "feet and maximum densities of eight units per acre."
)

_ENC_KW = dict(municipality="Encinitas", county="San Diego", state="CA", source_section_id="30.09")


def test_worded_density_is_captured_as_du_per_acre():
    rows = extract_dimensional_standards_from_prose(_ENCINITAS, **_ENC_KW)
    got = {r.district_code: r.max_density_units_per_acre for r in rows}
    assert got == {"R-3": 3.0, "R-5": 5.0}


def test_density_is_preferred_over_the_stated_lot_minimum():
    """Poway RS-7: 'minimum lot sizes of 4,500 square feet and maximum densities of
    eight units per acre'. 43,560/8 = 5,445 per unit, but the lot minimum is 4,500.

    Treating the lot minimum as the per-unit basis would compute 9 units on a
    43,560 sqft parcel where the ordinance allows 8 — over-counting, which inflates
    the purchase ceiling. The density is the ordinance's density rule; keep it."""
    rows = extract_dimensional_standards_from_prose(
        _POWAY_RS7,
        municipality="Poway",
        county="San Diego",
        state="CA",
        source_section_id="17.08.060",
    )
    assert len(rows) == 1
    row = rows[0]
    assert row.district_code == "RS-7"
    assert row.max_density_units_per_acre == 8.0
    assert row.min_lot_area_sqft is None
    assert row.to_numeric_zoning_params().min_lot_area_per_unit_sqft == 5445.0


def test_small_integer_densities_round_trip_exactly():
    """Storing density is only safe because these divide cleanly. 43,560/1,750 does
    not, which is why San Diego's per-unit-area statements are stored as areas."""
    for du in (2, 3, 4, 5, 8, 15, 20, 30):
        per_unit = 43560.0 / du
        assert per_unit == float(int(per_unit)), f"{du} du/acre does not divide cleanly"


# Verbatim Oceanside (Art.10), including the stray spaces its PDF inserts inside
# district codes ("RE -A") and the two densities stated in one sentence.
_OCEANSIDE_RE = (
    "Two types of Residential Estate districts are established: the Estate A (RE -A) "
    "District where the base density is 0.5 dwelling units per gross acre and the "
    "maximum potential density is 0.9 dwelling units per gross acre; and the Estate B "
    "District (RE-B) where the base density is 1.0 dwelling units per gross acre and "
    "the maximum potential density is 3.5 dwelling units per gross acre."
)

_OCEANSIDE_RH = (
    "In the RH District the base density is 21.0 dwelling units per gross acre and the "
    "maximum potential density is 28.9 units per gross acre; in the Urban High Density "
    "Residential District (RH-U) the base density is 29.0 dwelling units per gross acre "
    "and the maximum potential density is 43.0 dwelling units per gross acre."
)

_OCN_KW = dict(municipality="Oceanside", county="San Diego", state="CA", source_section_id="Art.10")


def test_oceanside_takes_base_density_never_maximum_potential():
    """THE correctness call for Oceanside.

    Every district states two densities. "Maximum potential" requires a density
    bonus or discretionary approval — it is not by-right. Taking 43.0 instead of
    29.0 for RH-U would overstate buildable units by ~48% and flow straight into
    an inflated purchase ceiling."""
    got = {
        r.district_code: r.max_density_units_per_acre
        for r in extract_dimensional_standards_from_prose(_OCEANSIDE_RH, **_OCN_KW)
    }
    assert got == {"RH": 21.0, "RH-U": 29.0}
    assert 28.9 not in got.values() and 43.0 not in got.values()


def test_stray_spaces_inside_a_district_code_are_normalised():
    """The PDF writes "RE -A". The stored code must be RE-A."""
    got = {
        r.district_code: r.max_density_units_per_acre
        for r in extract_dimensional_standards_from_prose(_OCEANSIDE_RE, **_OCN_KW)
    }
    assert got == {"RE-A": 0.5, "RE-B": 1.0}


def test_a_word_tail_is_never_mistaken_for_a_district_code():
    """Regression: under re.IGNORECASE, `[A-Z]{2,3}` matched lowercase and bound the
    tail of an ordinary word — "...RESIDENTIAL District..." produced a district
    literally named "IAL" carrying a real density. Case-sensitive code matching
    plus letter-boundary guards on both sides."""
    text = (
        "To provide opportunities for RESIDENTIAL District uses where the base "
        "density is 29.0 units per gross acre."
    )
    assert extract_dimensional_standards_from_prose(text, **_OCN_KW) == []


def test_a_single_letter_code_is_rejected():
    """ "the Estate B District" must not register a district called "B" — the real
    code is the parenthesised RE-B."""
    rows = extract_dimensional_standards_from_prose(_OCEANSIDE_RE, **_OCN_KW)
    assert "B" not in {r.district_code for r in rows}


# Verbatim El Cajon §17.15.010 "Establishment of zones by name".
_EL_CAJON_TABLE = (
    "| Zoning Districts: | Descriptive Zoning District Name: | | --- | --- | "
    "| O-S | Open Space | | H | Hillside Overlay | "
    "| PRD | Planned Residential Development | "
    "| RS-40 | Residential, Single-family, 40,000 square-foot | "
    "| RS-6 | Residential, Single-family, 6,000 square-foot | "
    "| RM-6000 | Residential, Multi-family 6,000 square-foot | "
    "| RM-2500 | Residential, Multi-family 2,500 square-foot | "
    "| RM-HR | Residential, Multi-family, High-Rise | "
    "| C-G | General Commercial | | M | Manufacturing |"
)

_ELC_KW = dict(
    municipality="El Cajon", county="San Diego", state="CA", source_section_id="17.15.010"
)


def test_el_cajon_reads_the_area_from_the_zones_descriptive_name():
    """The value is spelled out in the zone's NAME, not in a dimensional column."""
    got = _codes(extract_dimensional_standards_from_prose(_EL_CAJON_TABLE, **_ELC_KW))
    assert got == {
        "RS-40": 40000.0,
        "RS-6": 6000.0,
        "RM-6000": 6000.0,
        "RM-2500": 2500.0,
    }


def test_the_numeric_suffix_alone_is_never_used():
    """RS-6 is 6,000 sqft but RM-2500 is 2,500 — the suffix means different things
    in the two series. Deriving the value from the code would be wrong by three
    orders of magnitude for every RS zone, so only the spelled-out figure counts."""
    got = _codes(extract_dimensional_standards_from_prose(_EL_CAJON_TABLE, **_ELC_KW))
    assert got["RS-6"] == 6000.0 and got["RM-2500"] == 2500.0


def test_rows_without_a_stated_area_are_skipped():
    """RM-HR (High-Rise) states no figure, and the commercial/open-space rows have
    none either. None of them may be invented."""
    got = _codes(extract_dimensional_standards_from_prose(_EL_CAJON_TABLE, **_ELC_KW))
    for absent in ("RM-HR", "O-S", "PRD", "C-G", "M", "H"):
        assert absent not in got


def test_a_district_with_neither_axis_is_not_emitted():
    text = "**R-9: Residential 9** is intended to provide for residential units."
    assert extract_dimensional_standards_from_prose(text, **_ENC_KW) == []


def test_rows_carry_provenance_and_default_to_unverified():
    rows = extract_dimensional_standards_from_prose(_RM_BLOCK, **_KW, source_url="http://x")
    r = rows[0]
    assert r.source_section_id == "Art.01 Div.04"
    assert r.source_url == "http://x"
    assert r.verification_status is VerificationStatus.UNVERIFIED
    assert r.is_verified_fact_source() is False
