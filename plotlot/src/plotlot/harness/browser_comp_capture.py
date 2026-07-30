from __future__ import annotations

import json
import shlex
from dataclasses import dataclass
from subprocess import CompletedProcess, TimeoutExpired, run
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from plotlot.harness.comparable_listing_search import ComparableListingQuery
from plotlot.config import settings
from plotlot.harness.contracts import JsonObject, SourceMode
from plotlot.harness.comparable_listing_candidates import normalize_listing_candidates


class BrowserCompCaptureSubject(BaseModel):
    model_config = ConfigDict(frozen=True)

    address: str = Field(min_length=3)
    county: str = Field(min_length=1)
    municipality: str | None = None
    state: str = Field(default="FL", min_length=2, max_length=2)
    lot_size_sqft: float = Field(default=0.0, ge=0.0)
    zoning_code: str | None = None


@dataclass(frozen=True, slots=True)
class BrowserCompCaptureResult:
    payload: JsonObject


def capture_public_listing_comps(
    subject: BrowserCompCaptureSubject,
    *,
    source_mode: SourceMode,
) -> BrowserCompCaptureResult:
    if source_mode is SourceMode.FIXTURE:
        return BrowserCompCaptureResult(payload=_fixture_payload(subject))
    if not settings.browser_comp_runner_command.strip():
        return BrowserCompCaptureResult(
            payload={
                "status": "unavailable",
                "provider": "browser_use",
                "strategy": "public_sold_listing_capture",
                "candidates": [],
                "warnings": [
                    "Browser comp capture is configured as an optional runner; "
                    "set PLOTLOT_BROWSER_COMP_RUNNER_COMMAND to enable live capture."
                ],
            }
        )
    return BrowserCompCaptureResult(payload=_run_browser_capture(subject))


def _fixture_payload(subject: BrowserCompCaptureSubject) -> JsonObject:
    key = subject.address.strip().casefold()
    if "45 nw 209" in key or "miami gardens" in key:
        candidates = [
            _candidate(
                title="17605 NW 19th Avenue, Miami Gardens, FL 33056 | Zillow",
                url="https://www.zillow.com/homedetails/17605-NW-19th-Ave-Miami-Gardens-FL-33056/44106704_zpid/",
                address_hint="17605 NW 19th Avenue, Miami Gardens, FL 33056",
                municipality="Miami Gardens",
                zip_code="33056",
                fit_score=0.89,
                lot_size_variance_ratio=0.109,
            ),
            _candidate(
                title="2940 NW 169th Ter, Miami Gardens, FL 33056 | Zillow",
                url="https://www.zillow.com/homedetails/2940-NW-169th-Ter-Miami-Gardens-FL-33056/455424748_zpid/",
                address_hint="2940 NW 169th Ter, Miami Gardens, FL 33056",
                municipality="Miami Gardens",
                zip_code="33056",
                fit_score=0.81,
                lot_size_variance_ratio=0.192,
            ),
        ]
    elif "fort lauderdale" in key or "1234 nw 15th st" in key:
        candidates = [
            _candidate(
                title="1401 NW 14th Ave, Fort Lauderdale, FL 33311 | Zillow",
                url="https://www.zillow.com/homedetails/1401-NW-14th-Ave-Fort-Lauderdale-FL-33311/fixture",
                address_hint="1401 NW 14th Ave, Fort Lauderdale, FL 33311",
                municipality="Fort Lauderdale",
                zip_code="33311",
                fit_score=0.91,
                lot_size_variance_ratio=0.083,
            )
        ]
    else:
        candidates = []
    return {
        "status": "success",
        "provider": "browser_use",
        "strategy": "public_sold_listing_capture",
        "candidates": candidates,
        "warnings": [],
    }


def _run_browser_capture(subject: BrowserCompCaptureSubject) -> JsonObject:
    command = settings.browser_comp_runner_command.strip()
    try:
        args = shlex.split(command)
    except ValueError as exc:
        return _error_payload(f"browser comp runner command is invalid: {exc}")
    if not args:
        return _error_payload("browser comp runner command is empty")
    try:
        process = run(
            args,
            input=subject.model_dump_json(),
            capture_output=True,
            check=False,
            text=True,
            timeout=settings.browser_comp_runner_timeout_seconds,
        )
    except FileNotFoundError:
        return _error_payload(f"browser comp runner not found: {args[0]}")
    except PermissionError:
        return _error_payload(f"browser comp runner is not executable: {args[0]}")
    except TimeoutExpired:
        return _error_payload(
            "browser comp runner timed out after "
            f"{settings.browser_comp_runner_timeout_seconds:g} seconds"
        )
    return _parse_runner_output(process, subject=subject)


def _error_payload(warning: str) -> JsonObject:
    return {
        "status": "error",
        "provider": "browser_use",
        "strategy": "public_sold_listing_capture",
        "candidates": [],
        "warnings": [warning],
    }


def _parse_runner_output(
    process: CompletedProcess[str], *, subject: BrowserCompCaptureSubject
) -> JsonObject:
    if process.returncode != 0:
        return _error_payload(process.stderr.strip() or "browser comp runner failed")
    try:
        payload = json.loads(process.stdout)
    except json.JSONDecodeError:
        return _error_payload("browser comp runner returned invalid JSON")
    if not isinstance(payload, dict):
        return _error_payload("browser comp runner payload must be an object")
    status = str(payload.get("status") or "success")
    candidates = payload.get("candidates")
    artifacts = payload.get("artifacts") if isinstance(payload.get("artifacts"), list) else []
    warnings = payload.get("warnings")
    return {
        "status": status,
        "provider": "browser_use",
        "strategy": str(payload.get("strategy") or "public_sold_listing_capture"),
        "candidates": _normalize_runner_candidates(
            candidates,
            subject=subject,
        ),
        "warnings": warnings if isinstance(warnings, list) else [],
        "artifacts": artifacts,
    }


def _normalize_runner_candidates(
    candidates: JsonValue,
    *,
    subject: BrowserCompCaptureSubject,
) -> list[JsonObject]:
    if not isinstance(candidates, list):
        return []
    raw_candidates = [candidate for candidate in candidates if isinstance(candidate, dict)]
    normalized = normalize_listing_candidates(
        raw_candidates,
        query=ComparableListingQuery(
            query="browser_use public sold listing capture",
            search_category="sold_land",
            window_months=12,
            purpose="browser_public_listing_capture",
            stop_rule="county_reconcile_captured_public_listing_candidates",
        ),
        subject_payload={
            "address": subject.address,
            "municipality": subject.municipality or "",
            "county": subject.county,
            "state": subject.state,
            "lot_size_sqft": subject.lot_size_sqft,
            "zoning_code": subject.zoning_code or "",
        },
    )
    return [
        {
            **candidate,
            "candidate_kind": "browser_listing_candidate",
            "captured_by": "browser_use",
        }
        for candidate in normalized
    ]


def _candidate(
    *,
    title: str,
    url: str,
    address_hint: str,
    municipality: str,
    zip_code: str,
    fit_score: float,
    lot_size_variance_ratio: float,
) -> JsonObject:
    return {
        "title": title,
        "url": url,
        "address_hint": address_hint,
        "description": "Browser-captured sold listing candidate from a public real-estate page.",
        "source_domain": urlparse(url).netloc,
        "candidate_kind": "browser_listing_candidate",
        "classification": "likely_vacant_land",
        "confidence": 0.94,
        "parsing_confidence": 0.98,
        "search_category": "sold_land",
        "search_window_months": 12,
        "fit_score": fit_score,
        "lot_size_variance_ratio": lot_size_variance_ratio,
        "municipality": municipality,
        "municipality_match": True,
        "zip_code": zip_code,
        "zip_match": False,
        "captured_by": "browser_use",
    }
