from __future__ import annotations

import uuid
from typing import Any

from plotlot.land_use.models import ToolContext


async def handle_draft_google_doc(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    title = str(args.get("title", "")).strip() or "Untitled Draft"
    content = str(args.get("content", "") or "").strip()
    evidence_ids = args.get("evidence_ids") or []
    if not isinstance(evidence_ids, list):
        evidence_ids = []

    draft_id = f"draft_doc_{uuid.uuid4()}"
    return {
        "status": "drafted",
        "draft": {
            "draft_id": draft_id,
            "title": title,
            "content_preview": content[:240],
            "evidence_ids": evidence_ids,
        },
        "artifacts": {
            "document": {
                "document_type": "google_doc_draft",
                "status": "draft",
                "metadata_json": {
                    "draft_id": draft_id,
                    "title": title,
                    "content": content,
                    "evidence_ids": evidence_ids,
                    "workspace_id": context.workspace_id,
                    "project_id": context.project_id,
                    "site_id": context.site_id,
                },
            }
        },
    }


async def handle_draft_email(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    to_raw = args.get("to") or []
    to_list = to_raw if isinstance(to_raw, list) else [str(to_raw)]
    to_list = [str(addr).strip() for addr in to_list if str(addr).strip()]
    subject = str(args.get("subject", "") or "").strip()
    body = str(args.get("body", "") or "").strip()
    evidence_ids = args.get("evidence_ids") or []
    if not isinstance(evidence_ids, list):
        evidence_ids = []

    draft_id = f"draft_email_{uuid.uuid4()}"
    return {
        "status": "drafted",
        "draft": {
            "draft_id": draft_id,
            "to": to_list,
            "subject": subject,
            "body_preview": body[:240],
            "evidence_ids": evidence_ids,
        },
        "artifacts": {
            "document": {
                "document_type": "email_draft",
                "status": "draft",
                "metadata_json": {
                    "draft_id": draft_id,
                    "to": to_list,
                    "subject": subject,
                    "body": body,
                    "evidence_ids": evidence_ids,
                    "workspace_id": context.workspace_id,
                    "project_id": context.project_id,
                    "site_id": context.site_id,
                },
            }
        },
    }


async def handle_create_spreadsheet(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.retrieval.google_workspace import create_spreadsheet

    title = str(args.get("title", "") or "Untitled Spreadsheet").strip()
    headers = [str(header) for header in (args.get("headers") or [])]
    rows = [[str(cell) for cell in row] for row in (args.get("rows") or [])]

    try:
        result = await create_spreadsheet(title, headers, rows)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to create spreadsheet: {type(exc).__name__}: {exc}",
        }
    return {
        "status": "success",
        "spreadsheet_url": result.spreadsheet_url,
        "title": result.title,
        "row_count": len(rows),
    }


async def handle_create_document(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    from plotlot.retrieval.google_workspace import create_document

    title = str(args.get("title", "") or "Untitled Document").strip()
    content = str(args.get("content", "") or "")
    try:
        result = await create_document(title, content)
    except Exception as exc:
        return {
            "status": "error",
            "message": f"Failed to create document: {type(exc).__name__}: {exc}",
        }
    return {"status": "success", "document_url": result.document_url, "title": result.title}


async def handle_gmail_send_draft(args: dict[str, Any], context: ToolContext) -> dict[str, Any]:
    draft_id = str(args.get("draft_id", "") or "").strip()
    return {
        "status": "not_configured",
        "result": {"draft_id": draft_id},
        "message": "Gmail send is connected to policy but no live Gmail connector is configured.",
    }
