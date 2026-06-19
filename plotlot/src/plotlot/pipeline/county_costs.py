def get_construction_cost_psf(county: str = "", state: str = "FL") -> float:
    return 195.0 if county and "miami" in county.lower() else 175.0
