from pathlib import Path

from plotlot.api.main import app
from plotlot.storage.models import Analysis, AnalysisRun, Project, Site, Workspace


def test_plotlot_exposes_host_lifecycle_routes() -> None:
    # Given
    route_paths = {route.path for route in app.routes}

    # When
    lifecycle_routes = {
        path
        for path in route_paths
        if any(segment in path for segment in ("workspace", "project", "site", "analys"))
    }

    # Then
    assert lifecycle_routes
    assert any(path.startswith("/api/") for path in lifecycle_routes)


def test_plotlot_owns_the_lifecycle_model_chain() -> None:
    # Given / When
    table_names = [
        Workspace.__tablename__,
        Project.__tablename__,
        Site.__tablename__,
        Analysis.__tablename__,
        AnalysisRun.__tablename__,
    ]

    # Then
    assert table_names == ["workspaces", "projects", "sites", "analyses", "analysis_runs"]


def test_plotlot_keeps_clerk_at_the_frontend_edge() -> None:
    # Given
    app_root = Path(__file__).parents[2]
    proxy = (app_root / "frontend" / "src" / "proxy.ts").read_text(encoding="utf-8")

    # When
    clerk_edge_imported = '@clerk/nextjs/server"' in proxy

    # Then
    assert clerk_edge_imported
    assert not (app_root / "apps" / "web").exists()
