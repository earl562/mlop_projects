"""Assembly engine — filter, evaluate, resolve, sort, render clauses.

Takes an AssemblyConfig + DealContext, queries the ClauseRegistry,
applies conditions and group resolution, renders Jinja2 templates,
and delegates to the appropriate renderer for final output.
"""

from __future__ import annotations

import logging
import operator
import re
from datetime import datetime, timezone
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from plotlot.clauses.renderers.sheets_renderer import SheetsProFormaResult

import jinja2

from plotlot.clauses.loader import ClauseRegistry
from plotlot.clauses.schema import (
    AssemblyConfig,
    ContractClause,
    DealContext,
    GeneratedDocument,
    RenderedClause,
)

logger = logging.getLogger(__name__)

# Jinja2 environment — undefined vars render as [TBD]
_JINJA_ENV = jinja2.Environment(
    undefined=jinja2.ChainableUndefined,
    autoescape=False,
    keep_trailing_newline=True,
)

# Currency and number filters
_JINJA_ENV.filters["currency"] = lambda v: f"${v:,.0f}" if isinstance(v, (int, float)) else str(v)
_JINJA_ENV.filters["pct"] = lambda v: f"{v:.1f}%" if isinstance(v, (int, float)) else str(v)
_JINJA_ENV.filters["comma"] = lambda v: f"{v:,.0f}" if isinstance(v, (int, float)) else str(v)


# ---------------------------------------------------------------------------
# Condition expression evaluator (safe, no eval())
# ---------------------------------------------------------------------------

# Supported operators for condition expressions
_OPS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
}

# Pattern: context.field op value  OR  context.field in [val1, val2]
_CONDITION_RE = re.compile(r"^context\.(\w+)\s*(==|!=|>=?|<=?|in)\s*(.+)$")


def evaluate_condition(expr: str, context: DealContext) -> bool:
    """Safely evaluate a condition expression against a DealContext.

    Supports:
        context.field == 'value'
        context.field != 'value'
        context.field > 0
        context.field in ['a', 'b']

    Returns True if the condition is met, False otherwise.
    Unknown expressions return True (include by default).
    """
    match = _CONDITION_RE.match(expr.strip())
    if not match:
        logger.warning("Unparseable condition expression: %s", expr)
        return True  # include by default

    field, op_str, rhs_raw = match.groups()

    # Get field value from context
    value = getattr(context, field, None)
    if value is None:
        return False

    # Handle 'in' operator
    if op_str == "in":
        # Parse list-like RHS: ['a', 'b'] or [a, b]
        items_str = rhs_raw.strip().strip("[]").strip()
        if not items_str:
            return False  # empty list → always False
        items = [s.strip().strip("'\"") for s in items_str.split(",")]
        return str(value) in items

    # Parse RHS value
    rhs = rhs_raw.strip().strip("'\"")
    # Try numeric comparison
    try:
        rhs_num = float(rhs)
        value_num = float(value)
        return bool(_OPS[op_str](value_num, rhs_num))
    except (ValueError, TypeError):
        pass

    # String comparison
    return bool(_OPS[op_str](str(value), rhs))


# ---------------------------------------------------------------------------
# Group resolution
# ---------------------------------------------------------------------------


def resolve_groups(
    clauses: list[ContractClause],
    context: DealContext,
) -> list[ContractClause]:
    """For each group_id, keep only the clause whose condition matches.

    Clauses without a group_id pass through unchanged. Within a group,
    the first clause whose condition evaluates to True wins. If none
    match, all group clauses are excluded.
    """
    # Separate grouped from ungrouped
    ungrouped: list[ContractClause] = []
    groups: dict[str, list[ContractClause]] = {}

    for clause in clauses:
        if clause.group_id:
            groups.setdefault(clause.group_id, []).append(clause)
        else:
            ungrouped.append(clause)

    # Resolve each group
    selected: list[ContractClause] = list(ungrouped)
    for group_id, members in groups.items():
        winner: ContractClause | None = None
        for member in members:
            if member.condition_expr and evaluate_condition(member.condition_expr, context):
                winner = member
                break
            elif not member.condition_expr:
                # No condition — use as default/fallback
                if winner is None:
                    winner = member
        if winner:
            selected.append(winner)
        else:
            logger.debug("No matching clause in group '%s'", group_id)

    return selected


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render_clause(
    clause: ContractClause,
    context: DealContext,
    state_code: str = "FL",
) -> RenderedClause:
    """Render a single clause's Jinja2 template with the DealContext.

    Applies state variants if the state_code has an override template.
    Missing variables render as empty strings (ChainableUndefined).
    """
    # Choose template: state variant or default
    template_str = clause.content_template
    if clause.state_variants and state_code in clause.state_variants:
        template_str = clause.state_variants[state_code]

    # Render
    template = _JINJA_ENV.from_string(template_str)
    rendered = template.render(context=context)

    return RenderedClause(
        id=clause.id,
        title=clause.title,
        category=clause.category,
        rendered_content=rendered,
        formatting=clause.formatting,
        order_weight=clause.order_weight,
        is_required=clause.is_required,
    )


# ---------------------------------------------------------------------------
# Assembly pipeline
# ---------------------------------------------------------------------------


def assemble_clauses(
    config: AssemblyConfig,
    context: DealContext,
    registry: ClauseRegistry,
) -> list[RenderedClause]:
    """Run the full assembly pipeline: filter → evaluate → resolve → sort → render.

    Returns an ordered list of RenderedClause objects ready for a renderer.
    """
    # 1. Filter by document type + deal type
    candidates = registry.get(
        config.document_type,
        config.deal_type,
        exclude_ids=config.exclude_clause_ids,
    )
    logger.debug(
        "Filtered %d candidates for %s / %s",
        len(candidates),
        config.document_type.value,
        config.deal_type.value,
    )

    # 2. Evaluate conditions (non-group clauses)
    evaluated: list[ContractClause] = []
    for clause in candidates:
        if clause.condition_expr and not clause.group_id:
            if evaluate_condition(clause.condition_expr, context):
                evaluated.append(clause)
            else:
                logger.debug("Condition failed for %s: %s", clause.id, clause.condition_expr)
        else:
            evaluated.append(clause)

    # 3. Resolve mutually exclusive groups
    resolved = resolve_groups(evaluated, context)

    # 4. Apply order overrides
    if config.override_order:
        for clause in resolved:
            if clause.id in config.override_order:
                # Create a copy with overridden weight (clauses are immutable Pydantic models)
                pass  # override_order applied during sort

    # 5. Sort by order_weight
    def sort_key(c: ContractClause) -> int:
        if config.override_order and c.id in config.override_order:
            return config.override_order[c.id]
        return c.order_weight

    resolved.sort(key=sort_key)

    # 6. Render each clause
    rendered: list[RenderedClause] = []
    for clause in resolved:
        rendered.append(render_clause(clause, context, config.state_code))

    logger.info(
        "Assembled %d clauses for %s (%s)",
        len(rendered),
        config.document_type.value,
        config.deal_type.value,
    )
    return rendered


async def assemble_document(
    config: AssemblyConfig,
    context: DealContext,
    registry: ClauseRegistry,
) -> GeneratedDocument | SheetsProFormaResult:
    """Assemble a complete document from clauses.

    Delegates to the appropriate renderer based on config.output_format.
    Returns GeneratedDocument for file-based formats (docx, xlsx) or
    SheetsProFormaResult for google_sheets (contains shareable URL, no bytes).
    """
    if not context.generated_at:
        context.generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    rendered = assemble_clauses(config, context, registry)

    if config.output_format == "docx":
        from plotlot.clauses.renderers.docx_renderer import render_docx

        return render_docx(rendered, config, context)
    elif config.output_format == "xlsx":
        from plotlot.clauses.renderers.xlsx_renderer import render_xlsx

        return render_xlsx(rendered, config, context)
    elif config.output_format == "google_sheets":
        from plotlot.clauses.renderers.sheets_renderer import render_google_sheets

        return await render_google_sheets(rendered, config, context)
    else:
        raise ValueError(f"Unsupported output format: {config.output_format}")
