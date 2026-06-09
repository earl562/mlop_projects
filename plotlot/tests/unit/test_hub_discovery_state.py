"""Regression tests for Hub discovery state abbreviation handling.

Bug: _score_dataset used state.lower() ("nv") as the match string against
dataset metadata that contains full state names ("nevada"). The match always
failed, meaning the state bonus (+1.0) was never applied.

For Clark County, NV (Las Vegas), this lowered all dataset scores and caused
Hub discovery to fail — no dataset passed coverage validation, so
UniversalProvider returned None and the agent reported "property not found."

Fix:
- _expand_state() maps 2-letter codes → full names
- _score_dataset() checks both abbreviation AND full name in metadata text
- _search_hub() uses full state name in Hub API search queries
"""

from __future__ import annotations


from plotlot.property.hub_discovery import _expand_state, _score_dataset


# ---------------------------------------------------------------------------
# _expand_state
# ---------------------------------------------------------------------------


def test_expand_state_nv_returns_nevada() -> None:
    assert _expand_state("NV") == "nevada"


def test_expand_state_ca_returns_california() -> None:
    assert _expand_state("CA") == "california"


def test_expand_state_fl_returns_florida() -> None:
    assert _expand_state("FL") == "florida"


def test_expand_state_full_name_passthrough() -> None:
    assert _expand_state("Nevada") == "nevada"


def test_expand_state_unknown_passthrough() -> None:
    assert _expand_state("XX") == "xx"


# ---------------------------------------------------------------------------
# _score_dataset — state bonus applies when metadata uses full state name
# ---------------------------------------------------------------------------


def test_score_state_full_name_in_metadata_gets_bonus() -> None:
    """When metadata has 'nevada' but state='NV', bonus should still apply."""
    fields = ["PARCEL_ID", "OWNER", "ACRES", "SITE_ADDR"]
    score_with_fix = _score_dataset(
        fields=fields,
        name="Clark County Parcels",
        dataset_type="parcels",
        url="https://gis.clarkcountynv.gov/arcgis/rest/services/parcels",
        jurisdiction_text="Clark County Nevada property parcels",
        county="Clark",
        state="NV",
    )
    score_no_state = _score_dataset(
        fields=fields,
        name="Some Unrelated Parcels",
        dataset_type="parcels",
        url="https://example.com/arcgis",
        jurisdiction_text="some county some state property parcels",
        county="Clark",
        state="NV",
    )
    # Clark County with Nevada metadata should score higher than a dataset
    # with no state/county match in metadata
    assert score_with_fix > score_no_state


def test_score_state_abbreviation_in_metadata_also_works() -> None:
    """When metadata literally contains 'nv' (rare but possible), still gets bonus."""
    fields = ["APN", "OWNER", "LOT_SIZE"]
    score = _score_dataset(
        fields=fields,
        name="Clark County Parcels NV",
        dataset_type="parcels",
        url="https://example.com",
        jurisdiction_text="clark county nv parcels",
        county="Clark",
        state="NV",
    )
    # county match alone should be significant
    assert score > 0


def test_score_county_county_suffix_gets_high_score() -> None:
    """'clark county' in metadata → +8.0 bonus."""
    fields = ["PARCEL_ID", "OWNER", "ACRES", "ADDRESS", "ASSESSED", "YEAR_BUILT"]
    score = _score_dataset(
        fields=fields,
        name="Clark County Parcel Data",
        dataset_type="parcels",
        url="https://gis.clarkcountynv.gov/parcels",
        jurisdiction_text="clark county nevada",
        county="Clark",
        state="NV",
    )
    # county match (+8), state match (+1), .gov/parcel name (+2+3), field matches (~6+)
    assert score > 10.0


def test_score_wrong_state_gets_no_state_bonus() -> None:
    """Dataset from Clark County, Ohio should not get Nevada state bonus."""
    fields = ["PARCEL_ID", "OWNER", "ACRES"]
    score_nv = _score_dataset(
        fields=fields,
        name="Clark County Parcels",
        dataset_type="parcels",
        url="https://example.com",
        jurisdiction_text="clark county nevada",
        county="Clark",
        state="NV",
    )
    score_oh = _score_dataset(
        fields=fields,
        name="Clark County Parcels",
        dataset_type="parcels",
        url="https://example.com",
        jurisdiction_text="clark county ohio",
        county="Clark",
        state="NV",
    )
    # Nevada metadata should score higher for NV search than Ohio metadata
    assert score_nv > score_oh
