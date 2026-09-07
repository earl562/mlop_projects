# PlotLot Core Runtime Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shared PlotLot harness runtime execute and expose the four core product tools currently available only through the bespoke chat path: `analyze_property`, `calculate`, `analyze_upzoning`, and `screen_properties`.

**Architecture:** Add transport-neutral core decision-tool handlers in a focused harness module, register them with `build_default_runtime()`, and test handler behavior plus REST/MCP discovery parity. Existing deterministic pipeline functions remain the source of truth; this slice does not change chat or user-facing SSE contracts.

**Tech Stack:** Python 3.12, dataclasses, FastAPI, pytest/pytest-asyncio, Ruff, mypy, existing PlotLot deterministic pipeline and HarnessRuntime.

**Spec:** `docs/superpowers/specs/2026-08-20-plotlot-agentic-harness-consolidation-design.md`

## Global Constraints

- Preserve the existing deterministic parcel, zoning, feasibility, screening, and upzoning functions; do not add a second calculation engine.
- Tool handlers are transport-neutral: no FastAPI `Request`, chat `SessionStore`, SSE, or browser state.
- Every decision-relevant number must come from an existing deterministic function or a supplied input.
- `screen_properties` is approval/budget governed by its existing `EXPENSIVE_READ` contract.
- Batch screening is capped at 20 unique, non-empty addresses in this slice.
- Errors return structured dictionaries and do not leak unbounded exception text.
- No new production dependencies.
- Python changes must pass pytest, Ruff, and mypy under Python 3.12.

---

## File Structure

- Create `plotlot/src/plotlot/harness/core_decision_tools.py` — transport-neutral handlers and pure serializers for analysis, calculation, upzoning, and screening.
- Modify `plotlot/src/plotlot/harness/default_runtime.py` — register the four handlers through one `register_core_decision_tools(runtime)` call.
- Create `plotlot/tests/unit/test_core_decision_tools.py` — isolated handler tests with deterministic mocks and fixtures.
- Modify `plotlot/tests/unit/test_harness_runtime.py` — assert canonical registry/runtime parity for the four core tools.
- Modify `plotlot/tests/unit/test_tools_api.py` — assert REST and MCP discovery expose the same core tool names.

---

### Task 1: Lock the Runtime-Parity Contract with Failing Tests

**Files:**
- Modify: `plotlot/tests/unit/test_harness_runtime.py`
- Modify: `plotlot/tests/unit/test_tools_api.py`

**Interfaces:**
- Consumes: `build_default_runtime() -> HarnessRuntime`, `MCPAdapter.list_tools() -> list[dict[str, Any]]`.
- Produces: A test-level constant `CORE_DECISION_TOOLS: frozenset[str]` containing the four required tool names.

- [ ] **Step 1: Add the failing runtime registration test**

Append to `test_harness_runtime.py`:

```python
from plotlot.harness.default_runtime import build_default_runtime

CORE_DECISION_TOOLS = frozenset(
    {"analyze_property", "calculate", "analyze_upzoning", "screen_properties"}
)


def test_default_runtime_registers_core_decision_tools():
    runtime = build_default_runtime()
    missing = sorted(name for name in CORE_DECISION_TOOLS if not runtime.has_handler(name))
    assert missing == []
```

- [ ] **Step 2: Add the failing REST/MCP discovery parity test**

Append to `test_tools_api.py`:

```python
@pytest.mark.asyncio
async def test_rest_and_mcp_discover_all_core_decision_tools(client):
    from plotlot.harness.default_runtime import build_default_runtime
    from plotlot.harness.mcp_adapter import MCPAdapter

    expected = {"analyze_property", "calculate", "analyze_upzoning", "screen_properties"}

    response = await client.get("/api/v1/tools")
    assert response.status_code == 200
    rest_names = {item["name"] for item in response.json()}

    mcp_names = {item["name"] for item in MCPAdapter(build_default_runtime()).list_tools()}

    assert expected <= rest_names
    assert expected <= mcp_names
    assert rest_names == mcp_names
```

- [ ] **Step 3: Run the focused tests and verify the intended failure**

Run:

```bash
cd plotlot
pytest tests/unit/test_harness_runtime.py::test_default_runtime_registers_core_decision_tools \
       tests/unit/test_tools_api.py::test_rest_and_mcp_discover_all_core_decision_tools -q
```

Expected: both tests fail because the four handlers are not registered or returned by discovery.

- [ ] **Step 4: Commit the red tests**

```bash
git add -- plotlot/tests/unit/test_harness_runtime.py plotlot/tests/unit/test_tools_api.py
git commit -m "test(harness): require core decision tool parity"
```

---

### Task 2: Implement the Deterministic Calculation Handler

**Files:**
- Create: `plotlot/src/plotlot/harness/core_decision_tools.py`
- Create: `plotlot/tests/unit/test_core_decision_tools.py`

**Interfaces:**
- Produces: `handle_calculate(args: dict[str, Any], context: ToolContext) -> dict[str, Any]`.
- Consumes: `plotlot.pipeline.safe_calc.safe_calculate(expression: str) -> float` and `CalcError`.

- [ ] **Step 1: Write calculation tests**

Create `test_core_decision_tools.py` with:

```python
from __future__ import annotations

import pytest

from plotlot.harness.core_decision_tools import handle_calculate
from plotlot.land_use import ToolContext


def _context(*, budget: int = 0) -> ToolContext:
    return ToolContext(
        workspace_id="ws_test",
        actor_user_id="user_test",
        run_id="run_test",
        risk_budget_cents=budget,
        approved_approval_ids=set(),
    )


@pytest.mark.asyncio
async def test_handle_calculate_returns_clean_whole_number():
    result = await handle_calculate({"expression": "12 * 450000"}, _context())
    assert result == {
        "status": "success",
        "expression": "12 * 450000",
        "result": 5_400_000,
    }


@pytest.mark.asyncio
async def test_handle_calculate_rejects_non_arithmetic_expression():
    result = await handle_calculate({"expression": "__import__('os').system('id')"}, _context())
    assert result["status"] == "error"
    assert result["expression"] == "__import__('os').system('id')"
    assert "arithmetic" in result["message"].lower()
```

- [ ] **Step 2: Run the tests and verify import failure**

Run:

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py -q
```

Expected: collection fails because `plotlot.harness.core_decision_tools` does not exist.

- [ ] **Step 3: Implement the module shell and calculation handler**

Create `core_decision_tools.py`:

```python
"""Transport-neutral deterministic decision tools for the PlotLot harness."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from typing import Any

from plotlot.harness.runtime import HarnessRuntime
from plotlot.land_use.models import ToolContext

MAX_SCREEN_ADDRESSES = 20


async def handle_calculate(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    del context
    from plotlot.pipeline.safe_calc import CalcError, safe_calculate

    expression = str(args.get("expression") or "").strip()
    if not expression:
        return {"status": "error", "expression": expression, "message": "expression is required"}

    try:
        result = safe_calculate(expression)
    except CalcError as exc:
        return {
            "status": "error",
            "expression": expression,
            "message": (
                f"Could not evaluate the expression: {exc}. "
                "Pass arithmetic only using numbers, parentheses, and + - * / // % **."
            )[:300],
        }

    value: float | int = int(result) if result == int(result) else round(result, 4)
    return {"status": "success", "expression": expression, "result": value}
```

- [ ] **Step 4: Run calculation tests**

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit calculation handler**

```bash
git add -- plotlot/src/plotlot/harness/core_decision_tools.py \
           plotlot/tests/unit/test_core_decision_tools.py
git commit -m "feat(harness): add deterministic calculation handler"
```

---

### Task 3: Implement the Upzoning Handler

**Files:**
- Modify: `plotlot/src/plotlot/harness/core_decision_tools.py`
- Modify: `plotlot/tests/unit/test_core_decision_tools.py`

**Interfaces:**
- Produces: `handle_analyze_upzoning(args: dict[str, Any], context: ToolContext) -> dict[str, Any]`.
- Consumes: `plotlot.pipeline.upzoning.analyze_upzoning(...)` and its dataclass result.

- [ ] **Step 1: Add tests for grounded and missing-value scenarios**

Append:

```python
@pytest.mark.asyncio
async def test_handle_analyze_upzoning_uses_supplied_value(monkeypatch):
    from types import SimpleNamespace
    from plotlot.harness.core_decision_tools import handle_analyze_upzoning

    baseline = SimpleNamespace(
        name="By right", yield_count=2, yield_basis="lots", value_per_yield=300_000,
        gross_value=600_000, instant_equity=50_000, formula="2 x 300000",
    )
    upzoned = SimpleNamespace(
        name="Upzoned", yield_count=4, yield_basis="lots", value_per_yield=300_000,
        gross_value=1_200_000, instant_equity=650_000, formula="4 x 300000",
    )
    analysis = SimpleNamespace(
        all_in_basis=550_000, value_source="override", baseline=baseline, upzoned=upzoned,
        value_uplift=600_000, equity_created=650_000, cost_per_yield=137_500,
        exit_options=["sell lots"], notes=[], warnings=[],
    )
    monkeypatch.setattr("plotlot.pipeline.upzoning.analyze_upzoning", lambda **kwargs: analysis)

    result = await handle_analyze_upzoning(
        {"lot_sqft": 20_000, "value_per_lot": 300_000, "upzoned_yield": 4}, _context()
    )

    assert result["status"] == "success"
    assert result["equity_created"] == 650_000
    assert result["upzoned"]["yield_count"] == 4
    assert result["value_source"] == "override"


@pytest.mark.asyncio
async def test_handle_analyze_upzoning_requires_positive_lot_area():
    from plotlot.harness.core_decision_tools import handle_analyze_upzoning

    result = await handle_analyze_upzoning({"lot_sqft": 0}, _context())
    assert result == {
        "status": "error",
        "message": "A positive lot_sqft is required for upzoning analysis.",
    }
```

- [ ] **Step 2: Run the two tests and verify the handler is missing**

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py -k upzoning -q
```

Expected: import or attribute failure for `handle_analyze_upzoning`.

- [ ] **Step 3: Implement numeric parsing, scenario serialization, and the handler**

Add:

```python
def _optional_number(args: dict[str, Any], key: str) -> float | None:
    value = args.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _positive_int(args: dict[str, Any], key: str) -> int | None:
    value = args.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0:
        return int(value)
    return None


def _serialize_upzoning_scenario(scenario: Any) -> dict[str, Any] | None:
    if scenario is None:
        return None
    return {
        "name": scenario.name,
        "yield_count": scenario.yield_count,
        "yield_basis": scenario.yield_basis,
        "value_per_yield": round(scenario.value_per_yield),
        "gross_value": round(scenario.gross_value),
        "instant_equity": round(scenario.instant_equity),
        "formula": scenario.formula,
    }


async def handle_analyze_upzoning(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    del context
    from plotlot.pipeline.upzoning import analyze_upzoning

    lot_sqft = _optional_number(args, "lot_sqft")
    if not lot_sqft or lot_sqft <= 0:
        return {
            "status": "error",
            "message": "A positive lot_sqft is required for upzoning analysis.",
        }

    analysis = analyze_upzoning(
        lot_sqft=lot_sqft,
        value_per_lot=_optional_number(args, "value_per_lot"),
        purchase_price=_optional_number(args, "purchase_price") or 0.0,
        entitlement_soft_costs=_optional_number(args, "entitlement_soft_costs") or 0.0,
        baseline_yield=_positive_int(args, "baseline_yield"),
        upzoned_yield=_positive_int(args, "upzoned_yield"),
        baseline_min_lot_area_sqft=_optional_number(args, "baseline_min_lot_area_sqft"),
        upzoned_min_lot_area_sqft=_optional_number(args, "upzoned_min_lot_area_sqft"),
        yield_basis=str(args.get("yield_basis") or "buildable lots"),
        value_source="comps" if args.get("value_source") == "comps" else "override",
    )
    return {
        "status": "success",
        "all_in_basis": round(analysis.all_in_basis),
        "value_source": analysis.value_source,
        "baseline": _serialize_upzoning_scenario(analysis.baseline),
        "upzoned": _serialize_upzoning_scenario(analysis.upzoned),
        "value_uplift": round(analysis.value_uplift),
        "equity_created": round(analysis.equity_created),
        "cost_per_yield": round(analysis.cost_per_yield),
        "exit_options": analysis.exit_options,
        "notes": analysis.notes,
        "warnings": analysis.warnings,
    }
```

- [ ] **Step 4: Run upzoning tests**

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py -k upzoning -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit the upzoning handler**

```bash
git add -- plotlot/src/plotlot/harness/core_decision_tools.py \
           plotlot/tests/unit/test_core_decision_tools.py
git commit -m "feat(harness): add deterministic upzoning handler"
```

---

### Task 4: Implement the Grounded Property-Analysis Handler

**Files:**
- Modify: `plotlot/src/plotlot/harness/core_decision_tools.py`
- Modify: `plotlot/tests/unit/test_core_decision_tools.py`

**Interfaces:**
- Produces:
  - `serialize_analysis_report(report: ZoningReport) -> dict[str, Any]`
  - `handle_analyze_property(args: dict[str, Any], context: ToolContext) -> dict[str, Any]`
- Consumes: `plotlot.pipeline.analyze.analyze_property_deep(address: str) -> ZoningReport | None`.

- [ ] **Step 1: Add handler tests with a minimal domain report**

Append:

```python
@pytest.mark.asyncio
async def test_handle_analyze_property_serializes_grounded_decision_fields(monkeypatch):
    from plotlot.core.types import (
        CompAnalysis,
        DensityAnalysis,
        LandProForma,
        PropertyRecord,
        ZoningReport,
    )
    from plotlot.harness.core_decision_tools import handle_analyze_property

    report = ZoningReport(
        address="123 Main St",
        formatted_address="123 Main St, Charlotte, NC",
        municipality="Charlotte",
        county="Mecklenburg",
        state="NC",
        zoning_district="N1-C",
        property_record=PropertyRecord(
            address="123 Main St",
            county="Mecklenburg",
            owner="Example Owner LLC",
            lot_size_sqft=10_000,
            lot_size_source="assessor",
        ),
        density_analysis=DensityAnalysis(
            max_units=4,
            governing_constraint="min_lot_area",
            constraints=[],
            confidence="high",
            origin="local_authority",
        ),
        comp_analysis=CompAnalysis(
            estimated_land_value=500_000,
            estimated_land_value_low=450_000,
            estimated_land_value_high=550_000,
            adv_per_unit=650_000,
            adv_source="comps",
        ),
        pro_forma=LandProForma(
            gross_development_value=2_600_000,
            max_land_price=700_000,
            impact_fees_per_unit=20_000,
            adv_per_unit=650_000,
            max_units=4,
            adv_source="comps",
            market="Charlotte",
        ),
    )
    monkeypatch.setattr(
        "plotlot.pipeline.analyze.analyze_property_deep",
        pytest.AsyncMock(return_value=report),
    )

    result = await handle_analyze_property({"address": "123 Main St"}, _context())

    assert result["status"] == "success"
    assert result["address"] == "123 Main St, Charlotte, NC"
    assert result["zoning_code"] == "N1-C"
    assert result["by_right"]["max_units"] == 4
    assert result["valuation"]["max_land_price_residual"] == 700_000
    assert result["valuation"]["adv_per_unit"] == 650_000
    assert result["owner"] == "Example Owner LLC"


@pytest.mark.asyncio
async def test_handle_analyze_property_requires_address():
    from plotlot.harness.core_decision_tools import handle_analyze_property

    result = await handle_analyze_property({"address": " "}, _context())
    assert result == {"status": "error", "message": "An address is required."}
```

- [ ] **Step 2: Run the analysis tests and verify failure**

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py -k analyze_property -q
```

Expected: handler or serializer missing.

- [ ] **Step 3: Implement focused report serialization**

Add pure helpers that safely serialize dataclasses and explicitly shape the trust-critical contract:

```python
def _dataclass_dict(value: Any) -> Any:
    if value is None:
        return None
    if is_dataclass(value):
        return asdict(value)
    return value


def serialize_analysis_report(report: Any) -> dict[str, Any]:
    property_record = report.property_record
    density = report.density_analysis
    verification = report.extraction_verification
    comps = report.comp_analysis
    pro_forma = report.pro_forma

    by_right = {
        "max_units": density.max_units if density else None,
        "governing_constraint": density.governing_constraint if density else "unknown",
        "confidence": density.confidence if density else "low",
        "origin": density.origin if density else "unknown",
        "verification": verification.overall if verification else "unverified",
        "offer_is_provisional": (
            verification.offer_is_provisional if verification else True
        ),
        "constraints": _dataclass_dict(density.constraints) if density else [],
    }

    valuation = {
        "estimated_land_value": comps.estimated_land_value if comps else None,
        "land_value_range": (
            [comps.estimated_land_value_low, comps.estimated_land_value_high]
            if comps else None
        ),
        "adv_per_unit": pro_forma.adv_per_unit if pro_forma else None,
        "adv_source": pro_forma.adv_source if pro_forma else "",
        "gross_development_value": (
            pro_forma.gross_development_value if pro_forma else None
        ),
        "max_land_price_residual": pro_forma.max_land_price if pro_forma else None,
        "impact_fees_per_unit": pro_forma.impact_fees_per_unit if pro_forma else None,
        "market": pro_forma.market if pro_forma else "",
    }

    return {
        "status": "success",
        "address": report.formatted_address or report.address,
        "municipality": report.municipality,
        "county": report.county,
        "state": report.state,
        "zoning_code": report.zoning_district,
        "zoning_description": report.zoning_description,
        "owner": property_record.owner if property_record else "",
        "lot_size_sqft": property_record.lot_size_sqft if property_record else None,
        "lot_size_source": property_record.lot_size_source if property_record else "",
        "by_right": by_right,
        "valuation": valuation,
        "sensitivity": _dataclass_dict(report.sensitivity),
        "entitlement": _dataclass_dict(report.entitlement),
        "site_risk": _dataclass_dict(report.site_risk),
        "coastal_height_overlay": _dataclass_dict(report.coastal_overlay),
        "development_activity": report.development_signals or {},
        "entitlement_timeline_risk": _dataclass_dict(report.entitlement_timeline_risk),
        "warnings": list(report.warnings),
        "sources": list(report.sources),
        "confidence": report.confidence,
    }
```

- [ ] **Step 4: Implement the asynchronous handler**

```python
async def handle_analyze_property(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    del context
    from plotlot.pipeline.analyze import analyze_property_deep

    address = str(args.get("address") or "").strip()
    if not address:
        return {"status": "error", "message": "An address is required."}

    try:
        report = await analyze_property_deep(address)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Analysis failed: {type(exc).__name__}: {exc}"[:300],
        }
    if report is None:
        return {"status": "not_found", "message": f"Could not analyze: {address}"}
    return serialize_analysis_report(report)
```

- [ ] **Step 5: Run analysis tests**

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py -k analyze_property -q
```

Expected: 2 passed.

- [ ] **Step 6: Commit the analysis handler**

```bash
git add -- plotlot/src/plotlot/harness/core_decision_tools.py \
           plotlot/tests/unit/test_core_decision_tools.py
git commit -m "feat(harness): add grounded property analysis handler"
```

---

### Task 5: Implement the Buy-Box Screening Handler

**Files:**
- Modify: `plotlot/src/plotlot/harness/core_decision_tools.py`
- Modify: `plotlot/tests/unit/test_core_decision_tools.py`

**Interfaces:**
- Produces: `handle_screen_properties(args: dict[str, Any], context: ToolContext) -> dict[str, Any]`.
- Consumes: `BuyBox`, `screen_addresses`, and `analyze_property_full`.

- [ ] **Step 1: Add screening tests**

Append:

```python
@pytest.mark.asyncio
async def test_handle_screen_properties_deduplicates_caps_and_serializes(monkeypatch):
    from types import SimpleNamespace
    from plotlot.harness.core_decision_tools import handle_screen_properties

    captured: dict[str, object] = {}

    async def fake_screen(addresses, buy_box, analyze, **kwargs):
        captured["addresses"] = addresses
        captured["max_results"] = buy_box.max_results
        return SimpleNamespace(
            total=len(addresses),
            qualified_count=1,
            qualified=[SimpleNamespace(
                address=addresses[0], max_units=6, max_land_price=900_000,
                zoning_district="RM-3-7", county="San Diego", state="CA",
                offer_is_provisional=False,
            )],
            rejected=[SimpleNamespace(address="2 Test St", reasons=["below residual"])],
            errors=[],
        )

    monkeypatch.setattr("plotlot.pipeline.screening.screen_addresses", fake_screen)

    result = await handle_screen_properties(
        {"addresses": ["1 Test St", "1 Test St", "2 Test St"], "max_results": 500},
        _context(budget=50),
    )

    assert captured["addresses"] == ["1 Test St", "2 Test St"]
    assert captured["max_results"] == 100
    assert result["status"] == "success"
    assert result["qualified_count"] == 1
    assert result["qualified"][0]["max_land_price"] == 900_000


@pytest.mark.asyncio
async def test_handle_screen_properties_requires_addresses():
    from plotlot.harness.core_decision_tools import handle_screen_properties

    result = await handle_screen_properties({"addresses": []}, _context(budget=50))
    assert result == {
        "status": "error",
        "message": "Provide at least one address to screen.",
    }
```

- [ ] **Step 2: Run screening tests and verify failure**

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py -k screen_properties -q
```

Expected: handler missing.

- [ ] **Step 3: Implement address normalization and screening serialization**

Add:

```python
def _normalized_addresses(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    unique: list[str] = []
    seen: set[str] = set()
    for value in raw:
        if not isinstance(value, str):
            continue
        address = value.strip()
        key = address.casefold()
        if not address or key in seen:
            continue
        seen.add(key)
        unique.append(address)
        if len(unique) == MAX_SCREEN_ADDRESSES:
            break
    return unique


def _screening_row(result: Any) -> dict[str, Any]:
    return {
        "address": result.address,
        "max_units": result.max_units,
        "max_land_price": round(result.max_land_price) if result.max_land_price is not None else None,
        "zoning": result.zoning_district,
        "county": result.county,
        "state": result.state,
        "offer_is_provisional": result.offer_is_provisional,
    }


async def handle_screen_properties(
    args: dict[str, Any], context: ToolContext
) -> dict[str, Any]:
    del context
    from plotlot.pipeline.analyze import analyze_property_full
    from plotlot.pipeline.screening import BuyBox, screen_addresses

    addresses = _normalized_addresses(args.get("addresses"))
    if not addresses:
        return {"status": "error", "message": "Provide at least one address to screen."}

    max_results = max(1, min(int(args.get("max_results", 25) or 25), 100))
    buy_box = BuyBox(
        states=args.get("states") or [],
        counties=args.get("counties") or [],
        zoning_prefixes=args.get("zoning_prefixes") or [],
        min_lot_sqft=args.get("min_lot_sqft"),
        max_lot_sqft=args.get("max_lot_sqft"),
        min_units=args.get("min_units"),
        min_residual=args.get("min_residual"),
        exclude_high_flood_risk=bool(args.get("exclude_high_flood_risk", False)),
        require_verified=bool(args.get("require_verified", False)),
        max_results=max_results,
    )

    async def analyze(address: str):
        return await analyze_property_full(address, with_comps=False)

    try:
        batch = await screen_addresses(
            addresses,
            buy_box,
            analyze,
            concurrency=4,
            per_item_timeout=90.0,
        )
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Screening failed: {type(exc).__name__}: {exc}"[:300],
        }

    return {
        "status": "success",
        "screened": batch.total,
        "qualified_count": batch.qualified_count,
        "qualified": [_screening_row(item) for item in batch.qualified],
        "rejected_count": len(batch.rejected),
        "rejected_sample": [
            {"address": item.address, "reasons": item.reasons}
            for item in batch.rejected[:5]
        ],
        "error_count": len(batch.errors),
    }
```

- [ ] **Step 4: Run screening tests**

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py -k screen_properties -q
```

Expected: 2 passed.

- [ ] **Step 5: Commit the screening handler**

```bash
git add -- plotlot/src/plotlot/harness/core_decision_tools.py \
           plotlot/tests/unit/test_core_decision_tools.py
git commit -m "feat(harness): add deterministic screening handler"
```

---

### Task 6: Register Core Handlers and Satisfy REST/MCP Parity

**Files:**
- Modify: `plotlot/src/plotlot/harness/core_decision_tools.py`
- Modify: `plotlot/src/plotlot/harness/default_runtime.py`
- Test: `plotlot/tests/unit/test_harness_runtime.py`
- Test: `plotlot/tests/unit/test_tools_api.py`

**Interfaces:**
- Produces: `register_core_decision_tools(runtime: HarnessRuntime) -> None`.
- Consumes: the four handlers implemented in Tasks 2–5.

- [ ] **Step 1: Add the registration function**

Append to `core_decision_tools.py`:

```python
def register_core_decision_tools(runtime: HarnessRuntime) -> None:
    runtime.register("analyze_property", handle_analyze_property)
    runtime.register("calculate", handle_calculate)
    runtime.register("analyze_upzoning", handle_analyze_upzoning)
    runtime.register("screen_properties", handle_screen_properties)
```

- [ ] **Step 2: Wire registration into the default runtime**

At the top of `default_runtime.py`, add:

```python
from plotlot.harness.core_decision_tools import register_core_decision_tools
```

In `build_default_runtime()`, immediately after `runtime = HarnessRuntime(policy=policy)`, add:

```python
register_core_decision_tools(runtime)
```

- [ ] **Step 3: Run the original red tests**

```bash
cd plotlot
pytest tests/unit/test_harness_runtime.py::test_default_runtime_registers_core_decision_tools \
       tests/unit/test_tools_api.py::test_rest_and_mcp_discover_all_core_decision_tools -q
```

Expected: 2 passed.

- [ ] **Step 4: Run all focused harness tests**

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py \
       tests/unit/test_harness_runtime.py \
       tests/unit/test_tools_api.py -q
```

Expected: all selected tests pass.

- [ ] **Step 5: Run static checks on changed source and tests**

```bash
cd plotlot
ruff check src/plotlot/harness/core_decision_tools.py \
           src/plotlot/harness/default_runtime.py \
           tests/unit/test_core_decision_tools.py \
           tests/unit/test_harness_runtime.py \
           tests/unit/test_tools_api.py
mypy src/plotlot/harness/core_decision_tools.py src/plotlot/harness/default_runtime.py
```

Expected: no Ruff or mypy errors.

- [ ] **Step 6: Commit registration and parity**

```bash
git add -- plotlot/src/plotlot/harness/core_decision_tools.py \
           plotlot/src/plotlot/harness/default_runtime.py \
           plotlot/tests/unit/test_core_decision_tools.py \
           plotlot/tests/unit/test_harness_runtime.py \
           plotlot/tests/unit/test_tools_api.py
git commit -m "feat(harness): connect core decision tools to shared runtime"
```

---

### Task 7: Branch Verification and Delivery Evidence

**Files:**
- Read: `.github/workflows/*`
- Read: `docs/BRANCH_DELIVERY_WORKFLOW.md`
- No source changes unless verification identifies a real defect.

**Interfaces:**
- Consumes: committed branch head.
- Produces: recorded verification evidence in the final work summary.

- [ ] **Step 1: Run the repository-level backend gate available in the execution environment**

```bash
cd plotlot
pytest tests/unit/test_core_decision_tools.py \
       tests/unit/test_harness_runtime.py \
       tests/unit/test_tools_api.py -q
ruff check src/plotlot/harness tests/unit/test_core_decision_tools.py \
           tests/unit/test_harness_runtime.py tests/unit/test_tools_api.py
mypy src/plotlot/harness/core_decision_tools.py src/plotlot/harness/default_runtime.py
```

Expected: all commands exit 0.

- [ ] **Step 2: Inspect GitHub Actions for the committed branch head**

Confirm every workflow associated with the final commit is either successful or report the exact failing job and log evidence. Do not claim CI success based only on local tests.

- [ ] **Step 3: Review the final diff for scope and duplication**

```bash
git status --short
git diff --stat HEAD~1..HEAD
git diff HEAD~1..HEAD -- \
  plotlot/src/plotlot/harness/core_decision_tools.py \
  plotlot/src/plotlot/harness/default_runtime.py \
  plotlot/tests/unit/test_core_decision_tools.py \
  plotlot/tests/unit/test_harness_runtime.py \
  plotlot/tests/unit/test_tools_api.py
```

Expected: no unrelated files and no transport-specific state inside `core_decision_tools.py`.

- [ ] **Step 4: Report the slice outcome**

The completion report must include:

- exact files changed
- commit SHAs
- focused test, Ruff, and mypy results
- GitHub Actions result or exact unresolved failure
- confirmation that `/api/v1/tools` and MCP now discover the four core tools
- remaining boundary: legacy chat still uses bespoke executors until Slice 2
