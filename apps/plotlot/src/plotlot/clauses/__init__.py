"""Clause Builder — modular contract document generation.

Decomposes legal contract templates into reusable clauses that can be
assembled into any document type for any deal type.
"""

from plotlot.clauses.schema import (
    AssemblyConfig,
    ClauseCategory,
    ClauseFormatting,
    ContractClause,
    DealContext,
    DealType,
    DocumentType,
)

__all__ = [
    "AssemblyConfig",
    "ClauseCategory",
    "ClauseFormatting",
    "ContractClause",
    "DealContext",
    "DealType",
    "DocumentType",
]
