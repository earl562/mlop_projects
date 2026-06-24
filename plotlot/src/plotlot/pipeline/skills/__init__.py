"""Skill handler registry for analysis execution."""

from plotlot.pipeline.skills.playwright_comps import (  # noqa: F401 — register via decorator
    handle_fetch_zillow_comps,
)
from plotlot.pipeline.skills.single_parcel_feasibility import (  # noqa: F401 — register via decorator
    handle_single_parcel_feasibility,
)
