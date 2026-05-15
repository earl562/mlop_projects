"""Download routes for server-local generated artifacts."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from plotlot.retrieval.local_artifacts import artifact_path

router = APIRouter(prefix="/api/v1/artifacts", tags=["artifacts"])


@router.get("/{filename}")
async def download_artifact(filename: str) -> FileResponse:
    """Download a generated local artifact by safe filename."""

    path = artifact_path(filename)
    if not path.exists() or not path.is_file():
        raise HTTPException(status_code=404, detail="Artifact not found")
    return FileResponse(path)
