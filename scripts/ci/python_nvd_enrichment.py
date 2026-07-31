from __future__ import annotations

import json
import subprocess
import urllib.parse

from pair_gate_types import JsonObject, JsonValue, require_list, require_object

NVD_URL = "https://services.nvd.nist.gov/rest/json/cves/2.0"
USER_AGENT = "PlotLot-Repository-Pair-Gate/1.0"
SEVERITY_ORDER = {"unknown": 0, "low": 1, "medium": 2, "high": 3, "critical": 4}


def metric_values(metrics: JsonObject) -> list[tuple[str, float | None]]:
    result: list[tuple[str, float | None]] = []
    for key in ("cvssMetricV40", "cvssMetricV31", "cvssMetricV30", "cvssMetricV2"):
        raw_values = metrics.get(key)
        if not isinstance(raw_values, list):
            continue
        for raw_value in raw_values:
            if not isinstance(raw_value, dict):
                continue
            data = raw_value.get("cvssData")
            if not isinstance(data, dict):
                continue
            severity_value = data.get("baseSeverity")
            score_value = data.get("baseScore")
            if isinstance(severity_value, str):
                score = float(score_value) if isinstance(score_value, (int, float)) else None
                result.append((severity_value.lower(), score))
    return result


def fetch_nvd(cve_ids: set[str]) -> tuple[str, dict[str, JsonObject], list[JsonValue]]:
    if not cve_ids:
        return "available", {}, []
    query = urllib.parse.urlencode({"cveIds": ",".join(sorted(cve_ids))})
    response = subprocess.run(
        [
            "curl",
            "--fail",
            "--silent",
            "--show-error",
            "--location",
            "--max-time",
            "45",
            "--user-agent",
            USER_AGENT,
            f"{NVD_URL}?{query}",
        ],
        check=False,
        capture_output=True,
        timeout=50,
    )
    if response.returncode != 0:
        return "unavailable", {}, []
    try:
        document = require_object(json.loads(response.stdout), "NVD response")
    except (json.JSONDecodeError, TypeError):
        return "unavailable", {}, []
    by_id: dict[str, JsonObject] = {}
    cached: list[JsonValue] = []
    for raw_wrapper in require_list(document.get("vulnerabilities"), "NVD vulnerabilities"):
        wrapper = require_object(raw_wrapper, "NVD vulnerability")
        cve = require_object(wrapper.get("cve"), "NVD CVE")
        identifier = cve.get("id")
        metrics = cve.get("metrics")
        if not isinstance(identifier, str) or not isinstance(metrics, dict):
            continue
        values = metric_values(metrics)
        severity, score = max(
            values or [("unknown", None)],
            key=lambda value: SEVERITY_ORDER.get(value[0], 0),
        )
        record: JsonObject = {
            "id": identifier,
            "severity": severity,
            "score": score,
            "lastModified": cve.get("lastModified"),
        }
        by_id[identifier] = record
        cached.append(record)
    return "available", by_id, cached
