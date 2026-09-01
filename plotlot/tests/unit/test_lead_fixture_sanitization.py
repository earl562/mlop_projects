"""Privacy and normalization tests for Drive-derived property evaluation cases."""

from __future__ import annotations

import pytest

from plotlot.evaluation.leads import (
    LeadPrivacyError,
    assert_fixture_is_sanitized,
    sanitize_lead_row,
)


def test_sanitize_lead_row_keeps_property_facts_and_discards_contact_data():
    case = sanitize_lead_row(
        {
            "Input_Property_Address": " 1706-1708 Dewey St # 1-2 ",
            "Input_Property_City": "Hollywood",
            "Input_Property_State": "fl",
            "County": "Broward",
            "Asking Price": "$725,000",
            "Lot Size": "12,500",
            "Zoning": "RM-18",
            "Owner Name": "Private Owner",
            "Owner Phone": "954-555-1212",
            "Owner Email": "owner@example.com",
            "Mailing Address": "Private mailing address",
            "Notes": "Call the owner after 5pm",
        },
        source_file_id="drive-sheet-1",
        source_row=17,
    )

    assert case is not None
    assert case.address == "1706-1708 Dewey St # 1-2"
    assert case.city == "Hollywood"
    assert case.state == "FL"
    assert case.county == "Broward"
    assert case.asking_price == 725_000
    assert case.lot_size_sqft == 12_500
    assert case.zoning_hint == "RM-18"
    payload = case.model_dump(mode="json")
    assert set(payload) == {
        "case_id",
        "address",
        "city",
        "state",
        "county",
        "parcel_id",
        "asking_price",
        "lot_size_sqft",
        "zoning_hint",
        "workflow",
        "source_file_id",
        "source_row",
    }
    assert "Private Owner" not in str(payload)
    assert "954-555-1212" not in str(payload)
    assert "owner@example.com" not in str(payload)


def test_sanitize_lead_row_returns_none_without_a_property_address():
    row = {"Owner Email": "owner@example.com", "City": "Hollywood"}

    assert (
        sanitize_lead_row(
            row,
            source_file_id="drive-sheet-1",
            source_row=2,
        )
        is None
    )


def test_stable_case_id_uses_normalized_property_identity():
    first = sanitize_lead_row(
        {
            "Address": "5201 NW 16th St",
            "City": "Plantation",
            "State": "FL",
        },
        source_file_id="sheet-a",
        source_row=2,
    )
    second = sanitize_lead_row(
        {
            "Property Address": " 5201 nw 16TH st ",
            "Property City": "plantation",
            "Property State": "fl",
        },
        source_file_id="sheet-b",
        source_row=99,
    )

    assert first is not None
    assert second is not None
    assert first.case_id == second.case_id


def test_fixture_validator_rejects_contact_keys_and_values():
    contact_key_fixture = [
        {
            "case_id": "case_1",
            "address": "1 Main St",
            "owner_email": "x@y.com",
        }
    ]
    email_value_fixture = [{"case_id": "case_1", "address": "owner@example.com"}]
    phone_value_fixture = [
        {
            "case_id": "case_1",
            "address": "1 Main St",
            "county": "954-555-1212",
        }
    ]

    with pytest.raises(LeadPrivacyError, match="owner_email"):
        assert_fixture_is_sanitized(contact_key_fixture)

    with pytest.raises(LeadPrivacyError, match="email-like value"):
        assert_fixture_is_sanitized(email_value_fixture)

    with pytest.raises(LeadPrivacyError, match="phone-like value"):
        assert_fixture_is_sanitized(phone_value_fixture)


def test_fixture_validator_accepts_property_only_cases():
    fixture = [
        {
            "case_id": "case_1",
            "address": "5201 NW 16th St",
            "city": "Plantation",
            "state": "FL",
            "county": "Broward",
            "asking_price": 450000,
        }
    ]

    assert_fixture_is_sanitized(fixture)
