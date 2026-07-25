from __future__ import annotations

from plotlot.harness.contracts import (
    AccessStatus,
    SourceMode,
    VideoSourceCatalogEntry,
    VideoSourceId,
)

YOUTUBE_ARV_URL = "https://www.youtube.com/watch?v=0IS1iFMJ8sQ"
YOUTUBE_ARV_VIDEO_ID = "0IS1iFMJ8sQ"


def fixture_video_sources(_source_mode: SourceMode) -> list[VideoSourceCatalogEntry]:
    return [
        VideoSourceCatalogEntry(
            video_source_id=VideoSourceId("video_youtube_arv_offer_0is1ifmj8sq"),
            provider="youtube",
            category="Development Deal Analysis",
            title="ARV, Comparable Sales, and Offer Analysis Fixture",
            page_url=YOUTUBE_ARV_URL,
            video_url=YOUTUBE_ARV_URL,
            embed_url=f"https://www.youtube.com/embed/{YOUTUBE_ARV_VIDEO_ID}",
            platform_video_id=YOUTUBE_ARV_VIDEO_ID,
            source_page_url=YOUTUBE_ARV_URL,
            access_status=AccessStatus.PUBLIC,
            metadata={
                "tags": [
                    "sales comps",
                    "ARV",
                    "offer analysis",
                    "rehab/flip deal analysis",
                    "comparable-sales methodology",
                    "acquisition underwriting",
                ]
            },
            source_mode=SourceMode.FIXTURE,
        ),
        VideoSourceCatalogEntry(
            video_source_id=VideoSourceId("video_rehabvaluator_land_offer_fixture"),
            provider="rehabvaluator",
            category="Development Deal Analysis",
            title="Vacant Land Max Offer Workflow Fixture",
            page_url="https://rehabvaluator.com/value-vacant-land",
            video_url=None,
            embed_url=None,
            platform_video_id=None,
            source_page_url="https://rehabvaluator.com/value-vacant-land",
            access_status=AccessStatus.REQUIRES_USER_PROVIDED_TRANSCRIPT,
            metadata={"tags": ["max land purchase price", "density study", "lender proposal"]},
            source_mode=SourceMode.FIXTURE,
        ),
    ]


def fixture_transcript_text(video: VideoSourceCatalogEntry) -> str:
    if video.platform_video_id == YOUTUBE_ARV_VIDEO_ID:
        return (
            "Start with comparable sales that match the subject property, location, "
            "condition, bedroom count, and finished square footage. Adjust the comps "
            "before calling a final ARV. Use the indicated ARV to calculate a maximum "
            "offer after repair costs, closing costs, selling costs, and target profit. "
            "If the comps are weak or outside the neighborhood, lower confidence and "
            "verify the value before making an acquisition offer."
        )
    return (
        "A land offer workflow starts with density, unit mix, build costs, rents, "
        "stabilized value, and residual land value. The offer should be backed by "
        "evidence, assumptions, and lender package exhibits."
    )
