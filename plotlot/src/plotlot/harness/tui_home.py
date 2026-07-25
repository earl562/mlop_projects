from __future__ import annotations

from typing import Final

from pydantic import JsonValue

from plotlot.harness.south_florida_gis import load_south_florida_gis_source_catalog
from plotlot.harness.training_ingestion import discover_training_video_sources
from plotlot.harness.tui import TuiPanel, TuiRenderRequest, TuiScreen, TuiScreenName, TuiStores

SCREEN_COMMANDS: Final = [
    "plotlot tui --screen run-monitor --run-id RUN_ID",
    "plotlot tui --screen evidence --run-id RUN_ID",
    "plotlot tui --screen verification --run-id RUN_ID",
    "plotlot tui --screen approvals --run-id RUN_ID",
    "plotlot tui --screen report --run-id RUN_ID",
    "plotlot tui --screen replay-debug --run-id RUN_ID",
    "plotlot tui --screen source-catalog",
    "plotlot tui --screen training",
]


def home_screen(request: TuiRenderRequest, stores: TuiStores) -> TuiScreen:
    runs = stores.run_store.list_runs()
    gis_sources = load_south_florida_gis_source_catalog(request.source_mode)
    videos = discover_training_video_sources(source_mode=request.source_mode)
    screens: list[JsonValue] = ["run-monitor", "evidence", "verification", "approvals"]
    screens.extend(["report", "replay-debug", "source-catalog", "training"])
    return TuiScreen(
        screen=TuiScreenName.HOME,
        title="PlotLot TUI Workbench",
        summary={
            "source_mode": request.source_mode.value,
            "run_count": len(runs),
            "gis_source_count": len(gis_sources),
            "training_video_count": len(videos),
            "screens": screens,
        },
        panels=[
            TuiPanel(title="Run Monitor", items=[{"command": SCREEN_COMMANDS[0]}]),
            TuiPanel(title="Training Corpus", items=[{"command": SCREEN_COMMANDS[-1]}]),
        ],
        commands=SCREEN_COMMANDS,
    )
