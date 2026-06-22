from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from plotlot.land_use.models import ToolContext


@dataclass
class RuntimeDataset:
    records: list[dict[str, Any]]
    search_params: dict[str, Any]
    query_description: str
    total_available: int
    fetched_at: str


RUNTIME_DATASETS: dict[str, RuntimeDataset] = {}


async def handle_search_properties(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.retrieval.bulk_search import (
        PropertySearchParams,
        bulk_property_search,
        compute_dataset_stats,
        describe_search,
    )

    ownership_years = args.get("ownership_min_years")
    max_sale_date = None
    if ownership_years:
        cutoff_year = datetime.now(timezone.utc).year - int(ownership_years)
        max_sale_date = f"{cutoff_year}-01-01"

    try:
        params = PropertySearchParams(
            county=str(args["county"]),
            state=args.get("state"),
            lat=args.get("lat"),
            lng=args.get("lng"),
            land_use_type=args.get("land_use_type"),
            city=args.get("city"),
            max_sale_date=max_sale_date,
            min_lot_size_sqft=args.get("min_lot_size_sqft"),
            max_lot_size_sqft=args.get("max_lot_size_sqft"),
            min_sale_price=args.get("min_sale_price"),
            max_sale_price=args.get("max_sale_price"),
            min_assessed_value=args.get("min_assessed_value"),
            max_assessed_value=args.get("max_assessed_value"),
            year_built_before=args.get("year_built_before"),
            year_built_after=args.get("year_built_after"),
            owner_name_contains=args.get("owner_name_contains"),
            max_results=min(int(args.get("max_results", 500) or 500), 2000),
        )
        records = await bulk_property_search(params)
    except Exception as exc:
        return {
            "status": "error",
            "results": [],
            "message": f"Property search failed: {type(exc).__name__}: {exc}",
        }

    dataset = RuntimeDataset(
        records=records,
        search_params=dict(args),
        query_description=describe_search(args),
        total_available=len(records),
        fetched_at=datetime.now(timezone.utc).isoformat(),
    )
    RUNTIME_DATASETS[context.run_id] = dataset
    return {
        "status": "success",
        "total_results": len(records),
        "sample": records[:10],
        "stats": compute_dataset_stats(records),
        "dataset_key": context.run_id,
        "message": f"Found {len(records)} properties. Use filter_dataset or export_dataset with the same run_id.",
    }


async def handle_filter_dataset(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.retrieval.bulk_search import _safe_filter, compute_dataset_stats

    dataset = RUNTIME_DATASETS.get(context.run_id)
    if not dataset or not dataset.records:
        return {
            "status": "empty",
            "message": "No dataset in this run. Call search_properties first with the same run_id.",
        }

    records = list(dataset.records)
    expression = str(args.get("filter_expression", "") or "").strip()
    if expression:
        records = _safe_filter(records, expression)

    sort_by = str(args.get("sort_by", "") or "").strip()
    if sort_by and records and sort_by in records[0]:
        reverse = str(args.get("sort_order", "desc")).lower() == "desc"
        records = sorted(records, key=lambda record: record.get(sort_by, 0) or 0, reverse=reverse)

    limit = args.get("limit")
    if limit:
        records = records[: int(limit)]

    RUNTIME_DATASETS[context.run_id] = RuntimeDataset(
        records=records,
        search_params=dataset.search_params,
        query_description=f"{dataset.query_description} (filtered)"
        if expression
        else dataset.query_description,
        total_available=dataset.total_available,
        fetched_at=dataset.fetched_at,
    )
    if args.get("summary_only"):
        return {"status": "success", "count": len(records), "stats": compute_dataset_stats(records)}
    return {
        "status": "success",
        "total_after_filter": len(records),
        "sample": records[:10],
        "stats": compute_dataset_stats(records),
        "message": f"Filtered to {len(records)} properties.",
    }


async def handle_get_dataset_info(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.retrieval.bulk_search import compute_dataset_stats

    dataset = RUNTIME_DATASETS.get(context.run_id)
    if not dataset or not dataset.records:
        return {
            "status": "empty",
            "message": "No dataset in this run. Call search_properties first with the same run_id.",
        }
    return {
        "status": "success",
        "count": len(dataset.records),
        "fields": list(dataset.records[0].keys()),
        "search_description": dataset.query_description,
        "fetched_at": dataset.fetched_at,
        "stats": compute_dataset_stats(dataset.records),
        "sample": dataset.records[:5],
    }


async def handle_export_dataset(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.retrieval.google_workspace import create_spreadsheet

    dataset = RUNTIME_DATASETS.get(context.run_id)
    if not dataset or not dataset.records:
        return {
            "status": "empty",
            "message": "No dataset in this run. Call search_properties first with the same run_id.",
        }

    include_fields = [
        str(field) for field in (args.get("include_fields") or list(dataset.records[0].keys()))
    ]
    title = str(args.get("title") or f"PlotLot - {dataset.query_description}").strip()
    headers = [field.replace("_", " ").title() for field in include_fields]
    rows = [[str(record.get(field, "")) for field in include_fields] for record in dataset.records]

    try:
        result = await create_spreadsheet(title, headers, rows)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to export dataset: {type(exc).__name__}: {exc}",
        }
    return {
        "status": "success",
        "spreadsheet_url": result.spreadsheet_url,
        "title": result.title,
        "row_count": len(rows),
    }
