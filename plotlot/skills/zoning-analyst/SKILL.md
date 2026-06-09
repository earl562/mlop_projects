---
name: zoning-analyst
description: Analyze zoning compliance for a proposed land development project. Checks permitted uses, height limits, setbacks, density, parking, overlay districts.
trust_tier: T2
verification_gate: G3
metadata:
  skill_type: interpreter
---

# Zoning Analyst Skill

## When to Use
Use this skill when a user asks about zoning compliance, whether a proposed use is permitted, setback requirements, building height limits, density calculations, or parking requirements for a specific parcel.

## What This Skill Does
This skill runs the `check_zoning()` interpreter function against the parcel's zoning data and the proposed use parameters. It returns a structured compliance result with pass/fail for each criterion, specific failure reasons, and evidence for every check.

## How to Use

```python
from plotlot.harness.interpreter_skills import check_zoning, ParcelZoning, ProposedUse

zoning = ParcelZoning(
    parcel_id="<from property lookup>",
    zone_district="<from zoning database>",
    permitted_uses=["<from zoning code>"],
    max_height_ft=<from zoning code>,
    min_setback_front_ft=<from zoning code>,
    parking_per_unit=<from zoning code>,
    overlay_districts=["<any applicable>"],
)

proposed = ProposedUse(
    use_type="<user's proposed use>",
    building_height_ft=<user's proposed height>,
    front_setback_ft=<user's proposed setback>,
    parking_spaces=<user's proposed parking>,
    unit_count=<user's proposed units>,
    lot_size_sqft=<from property data>,
)

result = check_zoning(zoning, proposed)
# result.passed -> True/False
# result.failures -> list of specific violations
# result.evidence -> per-criterion measurements
# result.requires_human_review -> True if overlay/special conditions
```

## Limitations
- Overlay districts and special conditions are flagged for human review but not automatically evaluated
- Parking requirements use jurisdiction defaults unless specific municipal code is loaded
- Density calculations assume standard acre definition (43,560 sqft)
- This skill does NOT check: environmental impact, traffic studies, community plan consistency, or affordable housing requirements

## Error Guidance
- If parcel_id not found: verify address with geocode_address tool first
- If zone_district unknown: use search_zoning_ordinance to find applicable code
- If permitted_uses empty: the zoning database may need ingestion for this jurisdiction