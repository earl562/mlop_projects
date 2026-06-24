from __future__ import annotations

import pytest

from plotlot.harness.report_artifacts import handle_generate_document
from plotlot.land_use.models import ToolContext


@pytest.mark.asyncio
async def test_generate_document_handler_blocks_unrecorded_evidence_ids() -> None:
    # Given: a document request cites evidence not recorded in the tool context.
    result = await handle_generate_document(
        {
            "title": "Evidence Memo",
            "evidence_ids": ["ev_unrecorded"],
            "sections": [
                {
                    "id": "zoning",
                    "title": "Zoning",
                    "claims": [
                        {
                            "key": "zoning.max_units",
                            "text": "The site supports the verified maximum unit count.",
                            "material": True,
                            "evidence_ids": ["ev_unrecorded"],
                        }
                    ],
                }
            ],
        },
        ToolContext(
            workspace_id="ws_test",
            actor_user_id="anonymous",
            run_id="run_document_unrecorded_evidence",
            project_id="project_document_unrecorded_evidence",
        ),
    )

    # When: the tool validates evidence lineage at the handler boundary.
    status = result["status"]

    # Then: report generation is blocked before artifact creation.
    assert status == "blocked"
    assert result["missing_evidence_ids"] == ["ev_unrecorded"]
    assert result["artifacts"] == {}
