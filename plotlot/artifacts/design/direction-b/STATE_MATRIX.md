# Semantic State Matrix

Status words are product meaning, not visual decoration. `verified` means a cited authority supports the displayed field at the recorded retrieval/version. `derived` means a deterministic calculation with cited inputs. `needs_verification` means a potentially material input is absent/stale/conditional. `conflict` means two relevant records disagree. `unavailable` means the record/layer cannot be retrieved. `not_enabled` means analysis is prohibited for the current market.

| Domain | Verified / derived behavior | Needs verification / conflict behavior | Unavailable / not enabled behavior | Allowed user action |
| --- | --- | --- | --- | --- |
| Parcel identity | Canonical APN/folio, jurisdiction, geometry source and match confidence shown | Candidate parcels side-by-side; no dossier calculation until confirmed | “Cannot resolve parcel identity”; map may show search area only | refine ID, choose candidate, upload survey/plat |
| Coverage | Display exact market phrase and policy scope | Municipality-conditional displays city condition and missing policy/record | Planned/not enabled disables feasibility controls, preserves locator/waitlist | view policy, set municipal context, request access |
| Zoning | District + ordinance record/date/citation | Conflicting designation is marked; use/capacity abstains | no zoning claim or permitted-use summary | replay records, request current zoning confirmation |
| Setbacks / dimensional rules | each dimension has units, qualifier, source | missing side/rear/front or exceptions marks buildable envelope incomplete | no buildable envelope; no maximum unit assertion | request rule table, upload verified schedule |
| Capacity / max units | formula, inputs, governor, result, citations shown | yield range only when all bounds are explicit; otherwise abstain | no unit count/capacity card; reason remains visible | resolve named input / request feasibility review |
| Constraints | explicit overlay result + source timestamp | overlapping layers/geometry mismatch appear as material constraint conflict | “Layer unavailable”, never “no constraint” | replay layer, consult specialist, upload study |
| Survey / plat | document type, page, date, boundary/exception extraction, source ID | incompatible boundary/bearing/area values create a conflict card | “No survey/plat source linked”; geometry certainty reduced | upload survey, order/obtain record |
| Comps | inclusion rule, date, distance/adjustment policy, source set version | thin/old/non-comparable set downgrades ceiling confidence | no market-derived price conclusion | expand source set / add vetted comps |
| Purchase ceiling | equation and conditions visible: revenue/units/costs/target margin/land basis | show a provisional range only if explicit inputs yield it; label excluded risks | suppress ceiling if capacity or comp basis is unresolved | resolve upstream facts, export assumptions |
| Evidence replay | source/excerpt/hash/version/transformation chain available | cites competing record versions and affected claims | redacted metadata only if source restricted/unavailable | request source, compare versions |
| Grounded LLM analysis | observations cite evidence IDs inline and link to replays | analysis says which claim it cannot reconcile and does not choose a side | analysis returns an abstention template, not general web knowledge | open evidence, create handoff |

## Coverage truth: copy and control behavior

| Market context | Exact UI copy | Atlas/locator | Feasibility / LLM / ceiling |
| --- | --- | --- | --- |
| Miami-Dade | `Miami-Dade private beta — parcel analysis enabled only within published beta scope.` | enabled where an eligible parcel resolves | enabled only when evidence state permits |
| Broward / Palm Beach | `Municipality-conditional — availability depends on the resolved municipality and published source coverage.` | jurisdiction/parcel lookup may proceed | disabled until municipal eligibility and required sources are confirmed |
| San Diego | `Planned — not enabled for parcel analysis.` | locator can capture interest or permitted public context | no zoning, capacity, LLM feasibility, or purchase ceiling result |

The “Broward / Palm Beach” phrase intentionally does not imply countywide coverage. “Miami-Dade private beta” is neither a general availability claim nor a guarantee of a particular municipality/record.

## State presentation requirements

- A status consists of icon + label + sentence explaining impact + action where one exists.
- Warnings persist at the derived fact and the source row; closing a notice cannot hide the semantic state.
- A blank map layer has no implicit meaning. It must say `No data returned`, `Layer unavailable`, or `No mapped feature in this source` as appropriate.
- `Not enabled` is terminal for calculations: neither empty zeroes nor approximate values are displayed.
- No state is conveyed through red/green alone, and no caution copy is tucked behind a tooltip.
