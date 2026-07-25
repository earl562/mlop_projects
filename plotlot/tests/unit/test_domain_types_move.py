"""Contract tests for Slice 2.4: shared types moved to plotlot.domain.types.

These pin two invariants of the move:

1. The 5 types named in the slice spec (ToolContract, ToolContext, PolicyDecision,
   EvidenceItem, ReportClaim) plus their supporting dependency types
   (EvidenceCitation, SourceType, EvidenceConfidence, ToolRiskClass,
   EvidenceBackedReportSection, DEFAULT_ORDINANCE_LEGAL_CAVEAT) live canonically
   in `plotlot.domain.types` and are re-exported from the `plotlot.domain`
   package namespace.
2. `plotlot.land_use` (package + `models` module) re-exports the SAME class
   objects — they are aliases, not parallel definitions. This guards against a
   future regression where someone re-derives the type in land_use, which would
   silently break `isinstance` checks across the two namespaces and resurrect the
   divergent-registry hazard the Codebase Patterns warn about.

`land_use/` is now a thin service module: the type definitions no longer live
there. The existing `test_land_use_tool_contracts.py` must still pass — that is
the behavior-level acceptance test; these are the move-level acceptance tests.
"""

from __future__ import annotations

from plotlot import domain
from plotlot.domain import types as domain_types
from plotlot.land_use import models as land_use_models


def _pairs() -> list[tuple[str, object, object]]:
    """(name, domain.types object, land_use.models object) for every moved type."""

    moved = [
        "DEFAULT_ORDINANCE_LEGAL_CAVEAT",
        "SourceType",
        "EvidenceConfidence",
        "ToolRiskClass",
        "EvidenceCitation",
        "EvidenceItem",
        "ReportClaim",
        "EvidenceBackedReportSection",
        "ToolContext",
        "PolicyDecision",
        "ToolContract",
    ]
    out: list[tuple[str, object, object]] = []
    for name in moved:
        d_obj = getattr(domain_types, name)
        lu_obj = getattr(land_use_models, name)
        out.append((name, d_obj, lu_obj))
    return out


def test_moved_types_live_in_domain_types():
    for name, d_obj, _ in _pairs():
        assert getattr(domain_types, name) is d_obj, f"{name} not found in plotlot.domain.types"
        assert getattr(domain, name) is d_obj, (
            f"{name} not re-exported from plotlot.domain package namespace"
        )


def test_land_use_re_exports_same_identity_not_parallel_definitions():
    for name, d_obj, lu_obj in _pairs():
        assert d_obj is lu_obj, (
            f"{name} in land_use.models is a different object than in domain.types — "
            "land_use must re-export, not redefine"
        )


def test_moved_types_still_importable_from_land_use_package():
    """Existing consumers do `from plotlot.land_use import ToolContract`; keep it working."""

    from plotlot.land_use import (
        DEFAULT_ORDINANCE_LEGAL_CAVEAT,
        EvidenceBackedReportSection,
        EvidenceCitation,
        EvidenceConfidence,
        EvidenceItem,
        PolicyDecision,
        ReportClaim,
        SourceType,
        ToolContext,
        ToolContract,
        ToolRiskClass,
    )

    # touch each name so the import isn't pruned + assert identity with domain
    for name, d_obj, _ in _pairs():
        imported = {
            "DEFAULT_ORDINANCE_LEGAL_CAVEAT": DEFAULT_ORDINANCE_LEGAL_CAVEAT,
            "EvidenceBackedReportSection": EvidenceBackedReportSection,
            "EvidenceCitation": EvidenceCitation,
            "EvidenceConfidence": EvidenceConfidence,
            "EvidenceItem": EvidenceItem,
            "PolicyDecision": PolicyDecision,
            "ReportClaim": ReportClaim,
            "SourceType": SourceType,
            "ToolContext": ToolContext,
            "ToolContract": ToolContract,
            "ToolRiskClass": ToolRiskClass,
        }[name]
        assert imported is d_obj, f"{name} from plotlot.land_use is not the domain canonical"


def test_service_specific_types_remain_in_land_use_models():
    """land_use/models.py keeps ordinance + layer query types (service-specific)."""

    service_specific = [
        "OrdinanceJurisdiction",
        "OrdinanceSearchArgs",
        "OrdinanceSearchResult",
        "LayerCandidate",
        "PropertyLayerQuery",
        "LayerType",
    ]
    for name in service_specific:
        assert hasattr(land_use_models, name), f"{name} must stay in land_use.models"
        assert not hasattr(domain_types, name), (
            f"{name} is land-use-service-specific and must NOT live in domain.types"
        )


def test_domain_does_not_import_land_use():
    """The domain layer must remain transport/service-free: no land_use imports.

    This is the architectural invariant that makes the move safe — domain.types
    can't create an import cycle back into land_use. Asserts over the module's
    parsed import statements, not its docstring prose.
    """

    import ast
    import inspect

    tree = ast.parse(inspect.getsource(domain_types))
    land_use_refs: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "plotlot.land_use" or alias.name.startswith("plotlot.land_use."):
                    land_use_refs.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "plotlot.land_use" or module.startswith("plotlot.land_use."):
                land_use_refs.append(module)
    assert not land_use_refs, (
        f"domain.types must not import from plotlot.land_use (found: {land_use_refs})"
    )
