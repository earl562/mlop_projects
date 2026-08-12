"""The grounded-analysis payload: the only numbers a narrator may cite.

`_format_grounded_analysis` renders a deterministic `ZoningReport` into the dict
that every agent-facing surface answers from — chat, the MCP server, the CLI, and
the REST `/tools/call` adapter. Nothing in it is model-authored: each value is
produced by the pipeline and carries its own provenance and verification state.

**Why this lives in `pipeline/` and not `api/chat.py`.** It used to live in the
chat module, so `harness/default_runtime.py` had to reach *upward* into the API
layer to serve an MCP or CLI tool call — a transport importing another transport
purely to borrow a formatter. The payload is not a chat concern; it is the
pipeline's own presentation of its results, and every transport is a peer consumer
of it. `api.chat` re-exports these names so existing imports keep working.
"""

from __future__ import annotations

from typing import Any

from plotlot.pipeline.trust import assess_by_right_trust


def _round(value: float | None, ndigits: int = 0) -> float | None:
    """Round a value for compact tool output, preserving None."""
    if value is None:
        return None
    return round(value, ndigits)


def _format_sensitivity(sens) -> dict:
    """Render the deterministic residual sensitivity into citable scenarios.

    ``sens.grid[row][col]`` is the max land price at construction $/sf (rows) ×
    ADV per unit (cols); negative means the deal no longer pencils. We pre-label
    each move as a percentage off the base case so the narrator can quote a stress
    result verbatim instead of inventing cost ranges (it previously freelanced
    "$150-200k/unit hard costs" and bogus negative-equity math).
    """
    base_row = sens.base_row_index
    base_col = sens.base_col_index
    base_constr = sens.row_values[base_row] if sens.row_values else 0.0
    base_adv = sens.col_values[base_col] if sens.col_values else 0.0

    def _pct(value: float, base: float) -> str:
        if not base:
            return ""
        delta = round((value / base - 1) * 100)
        return f"{delta:+d}%" if delta else "base"

    def _flag(cell: float) -> str:
        return "  (does not pencil)" if cell < 0 else ""

    scenarios: list[str] = []
    # Construction stress at base exit (vary the row).
    for i, constr in enumerate(sens.row_values):
        if i == base_row:
            continue
        cell = sens.grid[i][base_col]
        scenarios.append(
            f"Construction {_pct(constr, base_constr)} (${constr:,.0f}/sf): "
            f"${cell:,.0f}{_flag(cell)}"
        )
    # Exit stress at base construction (vary the column).
    for j, adv in enumerate(sens.col_values):
        if j == base_col:
            continue
        cell = sens.grid[base_row][j]
        scenarios.append(
            f"Exit {_pct(adv, base_adv)} (${adv:,.0f}/unit): ${cell:,.0f}{_flag(cell)}"
        )
    # Combined adverse stress: highest construction cost + one step below base exit
    # (a realistic "costs up AND exit soft" combo, more decision-relevant than the
    # extreme corner). Falls back to the bottom-left corner if exit has no base-1.
    if sens.row_values and sens.col_values:
        combo_col = base_col - 1 if base_col >= 1 else 0
        combo = sens.grid[-1][combo_col]
        scenarios.append(
            f"Construction {_pct(sens.row_values[-1], base_constr)} AND "
            f"Exit {_pct(sens.col_values[combo_col], base_adv)}: ${combo:,.0f}{_flag(combo)}"
        )

    return {
        "base_max_land_price": _round(sens.base_value),
        "base_construction_psf": base_constr,
        "base_adv_per_unit": base_adv,
        "scenarios": scenarios,
        "note": (
            "Max land price under stress. Negative = the deal does not pencil at "
            "that asking price. Cite these exact scenarios for construction/exit "
            "'what if' questions; do not invent cost or price ranges."
        ),
    }


def _format_grounded_analysis(report) -> dict:
    """Render a ZoningReport into the grounded payload the agent may cite.

    Every figure here is produced by the deterministic pipeline and carries its
    verification status. The agent is instructed (in the tool description and the
    system prompt) to repeat ONLY these numbers — never to compute or recall its
    own — which is what stops the chat agent from hallucinating unit counts,
    comps, fees, and flood zones the way it did before this tool existed.
    """
    out: dict[str, Any] = {
        "status": "success",
        "address": report.formatted_address or report.address,
        "municipality": report.municipality,
        "county": report.county,
        "state": report.state,
        "zoning_code": report.zoning_district or "",
        "zoning_description": report.zoning_description or "",
    }

    # Zoning provenance gates trust the same way lot-size provenance does: the
    # district selects every dimensional standard downstream. "gis" means it was
    # read off the parcel/zoning layer. "ordinance_extraction" means no parcel
    # zoning code existed and the model inferred the district from retrieved
    # ordinance text — an assumption that has returned different districts for the
    # same parcel across runs ("CFR-116" vs "C-2" on one West Palm Beach address).
    # Unlabelled, that value is indistinguishable from a lookup, and the grounding
    # note invites the agent to cite it as fact.
    zoning_source = (report.zoning_source or "") if report.zoning_district else ""
    out["zoning_source"] = zoning_source
    # A district now only exists when a parcel/zoning layer supplied it. When one
    # did not, the pipeline reports no district at all rather than the model's
    # reading of the ordinance — that pick had no parcel-specific evidence and was
    # sometimes not even a real district in the city. The candidate it searched is
    # surfaced under a name no narrator can mistake for a lookup.
    zoning_unconfirmed = not report.zoning_district
    if zoning_unconfirmed:
        out["zoning_code"] = None
        out["zoning_status"] = "not_determined"
        out["zoning_basis"] = (
            f"{report.municipality or 'This municipality'} has no parcel/zoning GIS layer "
            "wired, so this parcel's zoning district is NOT known. Do not state a "
            "district. Any standard below was retrieved without a confirmed district "
            "and must be presented as unconfirmed."
        )
        if report.unverified_district:
            out["unverified_district_candidate"] = report.unverified_district
            out["unverified_district_note"] = (
                f"{report.unverified_district!r} is the district the ordinance search "
                "was run against, NOT this parcel's zoning. It is a candidate only — "
                "never cite it as the parcel's district."
            )
    else:
        out["zoning_status"] = "confirmed"
        out["zoning_basis"] = "zoning district read from the parcel/zoning GIS layer"

    pr = report.property_record
    out["lot_size_sqft"] = _round(pr.lot_size_sqft, 0) if pr and pr.lot_size_sqft else None
    # Lot-size provenance gates trust: the unit count is lot ÷ min-lot-area, so a
    # count is only as firm as the lot area it was built on. "assessor" = the
    # recorded legal lot (authoritative); "geometry" = a GIS polygon estimate that
    # can diverge from the legal lot (it once read 6,471 vs the assessor's 7,710,
    # flipping 6↔7 units) — so a count on it is NOT firm. "" = unknown provider.
    lot_source = (pr.lot_size_source if pr else "") or ""
    out["lot_size_source"] = lot_source
    lot_unconfirmed = lot_source == "geometry"
    if lot_unconfirmed:
        out["lot_size_basis"] = (
            "lot area is a GIS parcel-polygon estimate, NOT the recorded legal lot — "
            "it can diverge from the assessor's figure; confirm before treating the "
            "unit count as firm"
        )
    elif lot_source == "assessor":
        out["lot_size_basis"] = (
            "lot area is the county assessor's recorded legal lot (authoritative)"
        )

    # Measured slope gates the count the same way lot provenance does, and for
    # the same reason: the formula is density x GROSS acres, which silently
    # assumes the whole lot is buildable. That holds in flat Florida and fails on
    # a San Diego hillside, where steep ground is deducted before density applies
    # (SDMC §143.0110 environmentally sensitive lands; Carlsbad sizes coverage off
    # "net developable acreage"). We do not guess the buildable area — inventing
    # one would produce a confident wrong number — we mark the count an upper bound.
    terrain = report.terrain
    slope_unconfirmed = bool(terrain and terrain.slope_constrained)
    if terrain is not None:
        out["terrain"] = {
            "mean_slope_pct": terrain.mean_slope_pct,
            "max_slope_pct": terrain.max_slope_pct,
            "elevation_differential_ft": terrain.elevation_differential_ft,
            "steep_fraction_pct": terrain.steep_pct,
            "is_steep_hillside": terrain.is_steep_hillside,
            "slope_constrained": terrain.slope_constrained,
            "summary": terrain.summary(),
            "source": terrain.source,
        }
        if slope_unconfirmed:
            out["buildable_area_basis"] = terrain.yield_caveat()
        else:
            out["buildable_area_basis"] = (
                f"parcel is effectively flat ({terrain.mean_slope_pct:.0f}% average slope) — "
                "gross lot area is a sound basis for the unit count"
            )

    # Owner of record (county assessor OWN_NAME1) — a deterministic lookup field,
    # never an LLM guess. Carried in the grounded payload so it PERSISTS across
    # turns: the per-turn grounding block used to drop it, which let the narrator
    # claim "owner is not in the dataset" on follow-ups even though the assessor
    # record reliably returns it. Keep it here so the count's data carrier also
    # carries the owner.
    if pr and pr.owner:
        out["owner"] = pr.owner

    density = report.density_analysis
    ev = report.extraction_verification
    if density is not None:
        # A count built on an unconfirmed (geometry) lot area cannot be firm even
        # when the ordinance rule itself verified — the INPUT is unverified. The
        # same holds for an inferred district: every standard behind the count was
        # read out of whichever district the model picked.
        #
        # The verdict is computed in pipeline/trust.py, NOT here, so the SSE route
        # reaches the same answer. When it lived inline in this function the web UI
        # silently applied a weaker test and showed the same parcel as firm.
        trust = assess_by_right_trust(report)
        provisional = trust.is_provisional
        out["by_right"] = {
            "max_units": density.max_units,
            "governing_constraint": density.governing_constraint,
            "confidence": density.confidence,
            "verification": trust.verification,
            "offer_is_provisional": provisional,
            "lot_size_confirmed": trust.lot_confirmed,
            "zoning_confirmed": trust.zoning_confirmed,
            # False = density was applied to gross lot area on sloped ground, so the
            # count is an upper bound rather than an achievable yield. Also false when
            # slope was never measured — `buildable_area_measured` separates the two.
            "buildable_area_confirmed": trust.buildable_area_confirmed,
            "buildable_area_measured": trust.slope_measured,
            # Deterministic explanations, echoed verbatim by the persistent re-render.
            "provisional_reasons": list(trust.reasons),
            "verified_drivers": [
                {
                    "field": f.field,
                    "label": f.label,
                    "status": f.status,
                    "source_value": f.source_value,
                    "citation": (f.citation[:240] if f.citation else ""),
                    "section": f.section,
                }
                for f in (ev.fields if ev else [])
            ],
        }
    else:
        out["by_right"] = None
        out["note"] = "No residential unit count could be computed for this parcel."

    comps = report.comp_analysis
    pf = report.pro_forma
    valuation: dict[str, Any] = {}
    if comps is not None:
        # A comps-derived land value only exists when comps were actually found.
        # When none were, these come back 0.0 — and "estimated land value: $0" is
        # a false statement about a real parcel (it renders as "$0" because
        # _fmt_money(0.0) is truthy), not a missing value. Emit None so every
        # consumer says "not available" and defers to max_land_price_residual.
        has_comp_value = (comps.estimated_land_value or 0) > 0
        valuation["estimated_land_value"] = (
            _round(comps.estimated_land_value) if has_comp_value else None
        )
        valuation["land_value_range"] = (
            [
                _round(comps.estimated_land_value_low),
                _round(comps.estimated_land_value_high),
            ]
            if has_comp_value
            else [None, None]
        )
        valuation["adv_per_unit"] = _round(comps.adv_per_unit)
        valuation["adv_per_unit_range"] = [
            _round(comps.adv_per_unit_low),
            _round(comps.adv_per_unit_high),
        ]
        valuation["adv_source"] = comps.adv_source or "regional_default"
        valuation["comp_confidence"] = round(comps.confidence, 2)
    if pf is not None:
        valuation["max_land_price_residual"] = _round(pf.max_land_price)
        valuation["gross_development_value"] = _round(pf.gross_development_value)
        valuation["impact_fees_per_unit"] = _round(pf.impact_fees_per_unit)
        # Full residual COST STACK. The narrator otherwise reconstructed this from the
        # inputs and got it wrong — it multiplied $/sf by the LOT area instead of the
        # buildable area, and dropped soft costs and builder margin entirely, so its
        # listed costs didn't reconcile to the (correct) residual. Surface the exact
        # computed line items so every breakdown is read, not re-derived.
        valuation["hard_costs"] = _round(pf.hard_costs)
        valuation["soft_costs"] = _round(pf.soft_costs)
        valuation["builder_margin"] = _round(pf.builder_margin)
        valuation["impact_fees_total"] = _round(pf.impact_fees)
        if pf.gross_development_value and pf.max_land_price is not None:
            valuation["residual_formula"] = (
                f"GDV ${_round(pf.gross_development_value):,.0f} "
                f"− hard ${_round(pf.hard_costs):,.0f} "
                f"− soft ${_round(pf.soft_costs):,.0f} "
                f"− builder margin ${_round(pf.builder_margin):,.0f} "
                f"− impact fees ${_round(pf.impact_fees):,.0f} "
                f"= max land ${_round(pf.max_land_price):,.0f}"
            )
        if pf.max_units and pf.avg_unit_size_sqft and pf.construction_cost_psf:
            valuation["hard_cost_basis"] = (
                f"hard costs = {pf.max_units} units × {pf.avg_unit_size_sqft:,.0f} sqft/unit "
                f"× ${pf.construction_cost_psf:,.0f}/sf (BUILDABLE area — never the lot area)"
            )
        # If a real itemized fee schedule is registered for this jurisdiction, emit
        # the verified line items (the agent MAY cite these). Otherwise the fee is a
        # single coarse regional aggregate — label it so the agent can't invent a
        # park/fire/police breakdown the data doesn't contain.
        from plotlot.pipeline.fee_schedule import get_fee_schedule

        fee_schedule = get_fee_schedule(report.state, report.county)
        if fee_schedule is not None and fee_schedule.is_itemized:
            dif_total = _round(fee_schedule.total_per_unit)
            valuation["impact_fee_breakdown"] = [
                {
                    "name": c.name,
                    "amount_per_unit": _round(c.amount_per_unit),
                    "citation": c.citation,
                }
                for c in fee_schedule.components
            ]
            eff = (
                f" (effective {fee_schedule.effective_date})" if fee_schedule.effective_date else ""
            )
            if fee_schedule.covers_all_fees:
                # Comprehensive schedule IS the fee basis (also drives the residual).
                valuation["impact_fees_per_unit"] = dif_total
                valuation["impact_fees_basis"] = f"itemized from {fee_schedule.source}{eff}"
            else:
                # Partial schedule (SD city DIFs only): itemize the verified DIFs, but
                # leave impact_fees_per_unit as the residual's conservative all-in so the
                # offer is never optimistically understated.
                valuation["itemized_city_dif_per_unit"] = dif_total
                valuation["impact_fees_basis"] = (
                    f"{fee_schedule.source}{eff}. Verified City DIFs total "
                    f"${dif_total:,.0f}/unit (the itemized line items below). The residual "
                    f"budgets a conservative ${valuation['impact_fees_per_unit']:,.0f}/unit "
                    "all-in because RTCIP (SANDAG), school (SDUSD), and water/sewer capacity "
                    "fees are separate and not itemized here. Cite the verified DIF line "
                    "items; present the rest as additional separate fees — never invent amounts."
                )
        else:
            valuation["impact_fees_basis"] = (
                "coarse regional aggregate (school/park/traffic/utility combined) — "
                "NOT an itemized published schedule; do not break it into line items"
            )
        valuation["construction_cost_psf"] = _round(pf.construction_cost_psf)
        valuation["adv_per_unit"] = _round(pf.adv_per_unit)
        # Pre-format the exit value unambiguously so the narrator can't read the
        # PER-UNIT ADV as a project total (it did: "$750,000 total ($125k/unit)").
        if pf.adv_per_unit and density is not None and density.max_units:
            valuation["exit_value_formula"] = (
                f"{density.max_units} units x ${_round(pf.adv_per_unit):,.0f}/unit "
                f"(ADV per unit) = ${_round(pf.gross_development_value):,.0f} gross "
                "development value (GDV). ADV is PER UNIT — never divide it by the "
                "unit count."
            )
        valuation["adv_source"] = pf.adv_source or valuation.get("adv_source", "")
        if valuation["adv_source"] == "override":
            # A hand-supplied comp. It is the best number available in markets with
            # no sold-price source, but it is the USER's figure, not PlotLot's —
            # say so, or a later reader mistakes their own input for evidence.
            valuation["adv_basis"] = (
                "exit value per unit was SUPPLIED BY THE USER, not derived by PlotLot. "
                "The residual, max land price and sensitivity grid are all built on it. "
                "Attribute it to the user; never cite it as a PlotLot comp or as market "
                "evidence."
            )
        elif valuation["adv_source"] != "comps":
            basis = (
                "regional market default — no local sold-unit comps were found; "
                "treat exit value and residual as estimates, not appraised"
            )
            # Carry the comps engine's own account of WHY. A dead provider and an
            # uncovered market both land on the regional default, but only one is
            # fixable, and "no comps were found" hides which one this is.
            why = next((n for n in (comps.notes if comps else []) if n), "")
            if why:
                basis += f". Reason: {why}"
            valuation["adv_basis"] = basis
        valuation["market"] = pf.market
    out["valuation"] = valuation or None

    # Deterministic residual sensitivity (Task 3) — surface it so stress questions
    # ("what if construction +20% / exit -10%?") are answered from the grid instead
    # of the narrator freelancing invented cost ranges.
    sens = report.sensitivity
    if sens is not None and sens.grid:
        out["sensitivity"] = _format_sensitivity(sens)

    ent = report.entitlement
    if ent is not None:
        out["entitlement"] = {
            "path": ent.path,
            "complexity": ent.complexity,
            "est_timeline_months": _round(ent.est_timeline_months, 1),
            "impact_fee_per_unit": _round(ent.impact_fee_per_unit),
            "impact_fees_total": _round(ent.impact_fees_total),
            "utilities_note": ent.utilities_note,
        }

    sr = report.site_risk
    if sr is not None:
        fz = sr.flood_zone
        out["site_risk"] = {
            "flood_zone": fz.zone if fz else None,
            "in_special_flood_hazard_area": bool(fz and fz.in_sfha),
            "flood_risk_level": fz.risk_level if fz else "undetermined",
            "has_wetlands": sr.has_wetlands,
            "overall_risk": sr.overall_risk,
            "airport_influence": list(sr.airport_influence),
            "risk_flags": list(sr.risk_flags),
            "data_sources": sr.data_sources,
        }
        geo = sr.geologic
        if geo is not None:
            out["site_risk"]["geologic_hazard"] = {
                "fault_zone": geo.fault_zone,
                "landslide_zone": geo.landslide_zone,
                "liquefaction_zone": geo.liquefaction_zone,
                "in_any_hazard_zone": geo.in_any_hazard_zone,
                "evaluated": geo.evaluated,
                "flags": list(geo.flags),
                "source": "California Geological Survey (CGS) Seismic Hazard Zones",
            }

    co = report.coastal_overlay
    if co is not None and co.status != "not_applicable":
        out["coastal_height_overlay"] = {
            "applies": co.applies,
            "height_limit_ft": co.height_limit_ft,
            "status": co.status,
            "citation": co.citation,
        }

    dev = report.development_signals
    if dev and dev.get("permit_count"):
        out["development_activity"] = {
            "permit_count": dev.get("permit_count"),
            "active_permit_count": dev.get("active_permit_count"),
            "permit_holders": list(dev.get("unique_permit_holders") or [])[:8],
            "data_source": dev.get("data_source"),
            "note": (
                "This parcel has development permits on record with the city — it may "
                "already be an active development (owned/entitled), NOT raw land. Surface "
                "this before any 'what can I pay for the land' framing; the residual "
                "assumes the site is available to acquire and re-entitle."
            ),
        }

    etr = report.entitlement_timeline_risk
    if etr is not None:

        def _ceqa_brief(d):
            return {
                "sch": d.sch_number,
                "type": d.doc_type,
                "status": d.status,
                "title": d.title[:120],
                "url": d.source_url,
                "match_basis": d.match_basis,
                "match_confidence": d.match_confidence,
            }

        out["entitlement_timeline_risk"] = {
            "est_months_min": round(etr.est_months_min, 1),
            "est_months_max": round(etr.est_months_max, 1),
            "risk_level": etr.risk_level,
            "confidence": etr.confidence,
            "key_drivers": list(etr.key_drivers),
            "active_permits_exist": etr.active_permits_exist,
            # Tier 1 (parcel-confirmed, drives the timeline) vs Tier 2 (verify-only).
            "ceqa_strong_matches": [_ceqa_brief(d) for d in etr.ceqa_documents],
            "ceqa_candidates": [_ceqa_brief(d) for d in etr.ceqa_candidates],
        }

    opr = report.opposition_risk
    if opr is not None:
        out["opposition_risk"] = {
            "risk_level": opr.risk_level,
            "flags": list(opr.flags),
            "assessment": opr.assessment[:500] if opr.assessment else "",
            "confidence": opr.confidence,
        }

    uplift = report.density_uplift
    if uplift is not None:
        out["ca_upside"] = {
            "base_units": uplift.base_units,
            "max_potential_units": uplift.max_potential_units,
            "note": "Statutory maxima/eligibility ceilings, separate from the firm by-right count.",
            "programs": [
                {
                    "name": p.name,
                    "statute": p.statute,
                    "eligibility": p.eligibility,
                    "additional_units": p.additional_units,
                    "potential_units": p.potential_units,
                }
                for p in uplift.programs
            ],
        }

    # Surface only USER-FACING warnings. The extraction-verification warnings
    # (e.g. "6 u/ac contradicts source min lot area", "FAR 1.5 vs source 4") are
    # internal density-reconciliation diagnostics — the conflict is already
    # represented in by_right.verified_drivers' statuses, and leaking them as
    # top-level warnings just confuses the user (Q1 polish). Keep genuinely
    # actionable ones (e.g. ADV is a regional estimate).
    ev_warnings = set(ev.warnings) if ev else set()
    user_warnings = [w for w in (report.warnings or []) if w not in ev_warnings]

    # Trust caveats are collected SEPARATELY from ordinary pipeline warnings, then
    # appended to `warnings` (so the tool-turn payload and any UI consumer are
    # unchanged) and also published under their own key.
    #
    # The separate key exists because the persistent re-render truncates warnings to
    # the first 4, and these three are appended LAST — so a parcel carrying four
    # pipeline warnings silently dropped every trust caveat from every follow-up
    # turn. The re-render now subtracts this list and renders it structurally, where
    # it cannot be truncated away.
    trust_caveats: list[str] = []
    if lot_unconfirmed and out.get("lot_size_sqft"):
        trust_caveats.append(
            f"Lot area ({out['lot_size_sqft']:,.0f} sqft) is a GIS parcel-polygon "
            "estimate, not the recorded legal lot — confirm with the county assessor; "
            "the by-right unit count is provisional until it is."
        )
    if zoning_unconfirmed:
        candidate = report.unverified_district
        trust_caveats.append(
            f"This parcel's zoning district is not known — {report.municipality or 'this city'} "
            "has no parcel/zoning GIS layer wired, and PlotLot will not infer a district "
            "from ordinance text."
            + (
                f" The ordinance search was run against {candidate!r} as a candidate only."
                if candidate
                else ""
            )
            + " Every dimensional standard below is unconfirmed until the district is."
        )
    if slope_unconfirmed and terrain is not None:
        trust_caveats.append(terrain.yield_caveat())
    if trust_caveats:
        out["trust_caveats"] = trust_caveats
        user_warnings.extend(trust_caveats)
    if user_warnings:
        out["warnings"] = user_warnings

    out["grounding_note"] = (
        "These are the ONLY figures you may cite for this property. Do not add, "
        "round differently, or invent any number. If a field is null or absent, "
        "tell the user it is not available rather than estimating. If "
        "by_right.offer_is_provisional is true, present the unit count and offer "
        "as PROVISIONAL, not firm."
    )
    return out
