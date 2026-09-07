from importlib import import_module
from importlib.util import find_spec
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from plotlot.comps import CompPolicy, CompSubject, SaleEvidence

InvalidFactory = Callable[[], SaleEvidence | CompSubject | CompPolicy]


def test_comp_contract_is_available_from_public_package() -> None:
    # Given the public package path agreed by the implementation plan
    package_name = "plotlot.comps"

    # When Python resolves the contract package
    package_spec = find_spec(package_name)

    # Then callers can import the contract without depending on implementation modules
    assert package_spec is not None


def test_qualification_function_is_exported_from_public_package() -> None:
    # Given the published public package
    comps_package = import_module("plotlot.comps")

    # When a caller looks up the qualification entrypoint
    entrypoint = getattr(comps_package, "qualify_comps", None)

    # Then the public contract exposes a callable entrypoint
    assert callable(entrypoint)


@pytest.mark.parametrize(
    "invalid_factory",
    [
        lambda: CompPolicy(as_of="20260904"),
        lambda: CompPolicy(as_of="2026-W36-5"),
        lambda: CompPolicy(as_of="2026-09-04", radius_miles=3.01),
        lambda: CompPolicy(as_of="2026-09-04", min_comps=2),
        lambda: CompPolicy(as_of="2026-09-04", min_comps=5, max_comps=4),
    ],
)
def test_policy_rejects_noncanonical_or_unsafe_bounds(invalid_factory: InvalidFactory) -> None:
    # Given policy input outside the repeatable evaluation contract
    create_policy = invalid_factory

    # When the boundary parses the policy
    with pytest.raises(ValidationError) as raised:
        create_policy()

    # Then validation fails before qualification begins
    assert raised.value.error_count() >= 1


@pytest.mark.parametrize(
    "invalid_factory",
    [
        lambda: SaleEvidence(evidence_id=" ", state="FL", county="Miami-Dade"),
        lambda: SaleEvidence(evidence_id="sale-1", state=" ", county="Miami-Dade"),
        lambda: SaleEvidence(evidence_id="sale-1", state="FL", county=" "),
        lambda: CompSubject(parcel_id=" ", state="FL", county="Miami-Dade"),
        lambda: CompSubject(parcel_id="0001", state=" ", county="Miami-Dade"),
        lambda: CompSubject(parcel_id="0001", state="FL", county=" "),
    ],
)
def test_required_identities_reject_blank_values(invalid_factory: InvalidFactory) -> None:
    # Given a boundary model with a blank required identity
    create_model = invalid_factory

    # When the boundary parses the model
    with pytest.raises(ValidationError) as raised:
        create_model()

    # Then blank identity data cannot enter qualification
    assert raised.value.error_count() >= 1


@pytest.mark.parametrize(
    "invalid_factory",
    [
        lambda: SaleEvidence(evidence_id="sale-1", state="FL", county="Miami-Dade", latitude=91),
        lambda: SaleEvidence(
            evidence_id="sale-1", state="FL", county="Miami-Dade", longitude=float("inf")
        ),
        lambda: SaleEvidence(
            evidence_id="sale-1", state="FL", county="Miami-Dade", units=1_000_001
        ),
        lambda: SaleEvidence(
            evidence_id="sale-1",
            state="FL",
            county="Miami-Dade",
            source_url="file:///private/evidence.json",
        ),
    ],
)
def test_evidence_rejects_invalid_coordinates_numbers_and_urls(
    invalid_factory: InvalidFactory,
) -> None:
    # Given evidence containing an invalid numeric or URL value
    create_evidence = invalid_factory

    # When the boundary parses the evidence
    with pytest.raises(ValidationError) as raised:
        create_evidence()

    # Then unsafe evidence cannot enter qualification
    assert raised.value.error_count() >= 1


def test_evidence_is_frozen_and_rejects_extra_fields() -> None:
    # Given a parsed immutable evidence record
    evidence = SaleEvidence(evidence_id="sale-1", state="FL", county="Miami-Dade")

    # When callers try to mutate it or add undeclared input
    with pytest.raises(ValidationError) as frozen_error:
        evidence.sale_date = "2026-01-01"
    with pytest.raises(ValidationError) as extra_error:
        SaleEvidence(evidence_id="sale-2", state="FL", county="Miami-Dade", invented_field=True)

    # Then both boundary violations are rejected
    assert (frozen_error.value.error_count(), extra_error.value.error_count()) == (1, 1)
