"""Golden test cases for Charlotte NC metro area.

Each case has an address and expected zoning attributes for regression testing.
These are for OFFLINE evaluation — they test the extraction logic, not live APIs.

Charlotte metro (Mecklenburg County) municipalities covered:
- Charlotte (city proper)
- Huntersville
- Cornelius
- Davidson
- Matthews
"""

NC_GOLDEN_CASES = [
    {
        "address": "300 S Tryon St, Charlotte, NC 28202",
        "municipality": "Charlotte",
        "county": "Mecklenburg",
        "state": "NC",
        "expected_zone_prefix": "UMUD",  # Uptown Mixed Use District
        "expected_fields": ["max_height", "setbacks"],
    },
    {
        "address": "9820 Gilead Rd, Huntersville, NC 28078",
        "municipality": "Huntersville",
        "county": "Mecklenburg",
        "state": "NC",
        "expected_zone_prefix": "R",  # Residential
        "expected_fields": ["max_height", "setbacks"],
    },
    {
        "address": "100 N Main St, Cornelius, NC 28031",
        "municipality": "Cornelius",
        "county": "Mecklenburg",
        "state": "NC",
        "expected_zone_prefix": "",  # Not yet verified
        "expected_fields": [],
    },
    {
        "address": "209 Delburg St, Davidson, NC 28036",
        "municipality": "Davidson",
        "county": "Mecklenburg",
        "state": "NC",
        "expected_zone_prefix": "V",  # Village
        "expected_fields": ["max_height"],
    },
    {
        "address": "100 Trade St, Matthews, NC 28105",
        "municipality": "Matthews",
        "county": "Mecklenburg",
        "state": "NC",
        "expected_zone_prefix": "",  # Not yet verified
        "expected_fields": [],
    },
]

# Required fields every golden case must have
REQUIRED_CASE_FIELDS = {
    "address",
    "municipality",
    "county",
    "state",
    "expected_zone_prefix",
    "expected_fields",
}

# Municipalities that should be covered in the NC golden dataset
NC_MUNICIPALITIES = {"Charlotte", "Huntersville", "Cornelius", "Davidson", "Matthews"}
