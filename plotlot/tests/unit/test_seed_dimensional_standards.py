from pathlib import Path
import runpy

from plotlot.domain.dimensional_standard import VerificationStatus


def test_seed_rows_preserve_verified_and_staged_source_boundaries():
    script = Path(__file__).parents[2] / "scripts" / "seed_dimensional_standards.py"
    rows = runpy.run_path(str(script))["ROWS"]

    statuses = {(row.municipality, row.district_code): row.verification_status for row in rows}

    assert {
        status
        for (municipality, _district), status in statuses.items()
        if municipality == "Fort Lauderdale"
    } == {VerificationStatus.VERIFIED}
    assert {
        status
        for (municipality, _district), status in statuses.items()
        if municipality in {"Miami", "Hollywood"}
    } == {VerificationStatus.STAGED}
