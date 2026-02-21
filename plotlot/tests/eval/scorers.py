"""Deterministic scorers for PlotLot evaluation.

All 7 scorers are pure functions — no LLM calls, no network, no DB.
They compare pipeline outputs against golden expectations using exact
match or numeric tolerance.

Usage:
    from tests.eval.scorers import ALL_SCORERS
    result = mlflow.genai.evaluate(data=..., scorers=ALL_SCORERS)
"""

from mlflow.entities import Feedback
from mlflow.genai.scorers import scorer

# Confidence level ordering for comparison
_CONFIDENCE_LEVELS = {"high": 3, "medium": 2, "low": 1}


@scorer
def zoning_district_match(outputs: dict, expectations: dict) -> bool:
    """Exact match on zoning district code (case-insensitive)."""
    expected = expectations.get("zoning_district", "")
    actual = outputs.get("zoning_district", "")
    return bool(actual.strip().lower() == expected.strip().lower())


@scorer
def municipality_match(outputs: dict, expectations: dict) -> bool:
    """Exact match on municipality name (case-insensitive)."""
    expected = expectations.get("municipality", "")
    actual = outputs.get("municipality", "")
    return bool(actual.strip().lower() == expected.strip().lower())


@scorer
def max_units_match(outputs: dict, expectations: dict) -> bool:
    """Exact match on calculated max units."""
    expected = expectations.get("max_units")
    actual = outputs.get("max_units")
    if expected is None or actual is None:
        return False
    return int(actual) == int(expected)


@scorer
def governing_constraint_match(outputs: dict, expectations: dict) -> bool:
    """Exact match on governing constraint name."""
    expected = expectations.get("governing_constraint", "")
    actual = outputs.get("governing_constraint", "")
    return bool(actual.strip().lower() == expected.strip().lower())


@scorer
def numeric_extraction_accuracy(outputs: dict, expectations: dict) -> Feedback:
    """Fraction of numeric params within tolerance (0.0–1.0).

    Compares each expected numeric param against actual. A param "matches"
    if the actual value is within (tolerance * expected) of expected.
    """
    expected_params = expectations.get("numeric_params", {})
    actual_params = outputs.get("numeric_params", {})
    tolerance = expectations.get("numeric_tolerance", 0.1)

    if not expected_params:
        return Feedback(name="numeric_extraction_accuracy", value=1.0, rationale="No params to check")

    matched = 0
    total = len(expected_params)
    details = []

    for key, expected_val in expected_params.items():
        actual_val = actual_params.get(key)
        if actual_val is None:
            details.append(f"{key}: MISSING (expected {expected_val})")
            continue

        try:
            expected_f = float(expected_val)
            actual_f = float(actual_val)
        except (ValueError, TypeError):
            details.append(f"{key}: PARSE ERROR (actual={actual_val}, expected={expected_val})")
            continue

        if expected_f == 0:
            if actual_f == 0:
                matched += 1
                details.append(f"{key}: OK (both 0)")
            else:
                details.append(f"{key}: MISMATCH (actual={actual_f}, expected=0)")
        else:
            relative_error = abs(actual_f - expected_f) / abs(expected_f)
            if relative_error <= tolerance:
                matched += 1
                details.append(f"{key}: OK (error={relative_error:.1%})")
            else:
                details.append(f"{key}: MISMATCH (actual={actual_f}, expected={expected_f}, "
                               f"error={relative_error:.1%} > {tolerance:.0%})")

    score = matched / total if total > 0 else 0.0
    return Feedback(
        name="numeric_extraction_accuracy",
        value=score,
        rationale=f"{matched}/{total} params within {tolerance:.0%} tolerance. " + "; ".join(details),
    )


@scorer
def confidence_acceptable(outputs: dict, expectations: dict) -> bool:
    """Confidence meets or exceeds expected minimum."""
    expected_min = expectations.get("confidence_min", "low")
    actual = outputs.get("confidence", "low")
    return _CONFIDENCE_LEVELS.get(actual, 0) >= _CONFIDENCE_LEVELS.get(expected_min, 0)


@scorer
def report_completeness(outputs: dict, expectations: dict) -> Feedback:
    """Fraction of required report fields that are populated (0.0–1.0).

    Checks: zoning_district, municipality, county, confidence, has_summary,
    has_allowed_uses, num_sources > 0.
    """
    checks = {
        "zoning_district": bool(outputs.get("zoning_district")),
        "municipality": bool(outputs.get("municipality")),
        "county": bool(outputs.get("county")),
        "confidence": outputs.get("confidence") in ("high", "medium", "low"),
        "has_summary": bool(outputs.get("has_summary")),
        "has_allowed_uses": bool(outputs.get("has_allowed_uses")),
        "has_sources": (outputs.get("num_sources") or 0) > 0,
    }

    passed = sum(checks.values())
    total = len(checks)
    score = passed / total if total > 0 else 0.0

    failed = [k for k, v in checks.items() if not v]
    rationale = f"{passed}/{total} fields populated"
    if failed:
        rationale += f". Missing: {', '.join(failed)}"

    return Feedback(name="report_completeness", value=score, rationale=rationale)


@scorer
def setback_accuracy(outputs: dict, expectations: dict) -> Feedback:
    """Fraction of setback params (front/side/rear) within tolerance (0.0-1.0).

    Setbacks are the most user-visible extraction — front/side/rear errors
    directly affect buildable envelope calculations. This scorer surfaces
    setback quality separately from the aggregate numeric_extraction_accuracy.
    """
    expected_params = expectations.get("numeric_params", {})
    actual_params = outputs.get("numeric_params", {})
    tolerance = expectations.get("numeric_tolerance", 0.1)

    setback_keys = ["setback_front_ft", "setback_side_ft", "setback_rear_ft"]
    expected_setbacks = {k: expected_params[k] for k in setback_keys if k in expected_params}

    if not expected_setbacks:
        return Feedback(
            name="setback_accuracy",
            value=1.0,
            rationale="No expected setbacks to check",
        )

    matched = 0
    total = len(expected_setbacks)
    details = []

    for key, expected_val in expected_setbacks.items():
        actual_val = actual_params.get(key)
        if actual_val is None:
            details.append(f"{key}: MISSING (expected {expected_val})")
            continue

        try:
            expected_f = float(expected_val)
            actual_f = float(actual_val)
        except (ValueError, TypeError):
            details.append(f"{key}: PARSE ERROR (actual={actual_val}, expected={expected_val})")
            continue

        if expected_f == 0:
            if actual_f == 0:
                matched += 1
                details.append(f"{key}: OK (both 0)")
            else:
                details.append(f"{key}: MISMATCH (actual={actual_f}, expected=0)")
        else:
            relative_error = abs(actual_f - expected_f) / abs(expected_f)
            if relative_error <= tolerance:
                matched += 1
                details.append(f"{key}: OK (error={relative_error:.1%})")
            else:
                details.append(
                    f"{key}: MISMATCH (actual={actual_f}, expected={expected_f}, "
                    f"error={relative_error:.1%} > {tolerance:.0%})"
                )

    score = matched / total if total > 0 else 0.0
    return Feedback(
        name="setback_accuracy",
        value=score,
        rationale=f"{matched}/{total} setbacks within {tolerance:.0%} tolerance. " + "; ".join(details),
    )


ALL_SCORERS = [
    zoning_district_match,
    municipality_match,
    max_units_match,
    governing_constraint_match,
    numeric_extraction_accuracy,
    setback_accuracy,
    confidence_acceptable,
    report_completeness,
]
