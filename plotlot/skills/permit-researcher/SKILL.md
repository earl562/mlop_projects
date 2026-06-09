---
name: permit-researcher
description: Identify all required permits for a land development project by type and jurisdiction. Returns required permits, conditional permits, and estimated timelines.
trust_tier: T2
verification_gate: G2
---

# Permit Researcher Skill

## When to Use
Use this skill when a user asks what permits are needed for a project, how long permitting takes, or what agencies to contact. Covers residential (1-4 units), multi-family (5+), commercial, and industrial project types.

## How to Use
```python
from plotlot.harness.interpreter_skills import identify_permits
result = identify_permits("multi_family", jurisdiction="Miami-Dade")
# result.evidence["required_permits"] → list of required permits
# result.evidence["conditional_permits"] → conditional permits
# result.evidence["estimated_timeline_weeks"] → total weeks
```

## Limitations
- Permit requirements are jurisdiction defaults. Actual requirements vary by municipality.
- Timelines are estimates based on typical processing times.
- Does not account for expedited review or variances.
- Always verify with the local building department.

## Critical Permits by Project Type

| Type | Key Permits |
|------|-------------|
| residential_new_construction | Building, Zoning, Site Development, Grading, Utility |
| multi_family | Building, Zoning, Conditional Use, Traffic Impact, Density Bonus |
| commercial | Building, Zoning, Conditional Use, Traffic Impact, Sign |