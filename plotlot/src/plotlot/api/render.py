"""Building render endpoint — AI-generated architectural visualizations.

Uses Google Gemini image generation to produce photorealistic renderings
from structured zoning/floor plan data, replacing the broken Three.js viewer.
Generates three views: front, aerial 3D, and side.
"""

import asyncio
import base64
import hashlib
import logging
import time
from collections import OrderedDict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from plotlot.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/render", tags=["render"])

# ---------------------------------------------------------------------------
# Request / Response models
# ---------------------------------------------------------------------------


class BuildingRenderRequest(BaseModel):
    property_type: str  # single_family, duplex, multifamily, commercial
    stories: int
    total_width_ft: float  # buildable footprint width
    total_depth_ft: float  # buildable footprint depth
    max_height_ft: float
    lot_width_ft: float
    lot_depth_ft: float
    zoning_district: str
    unit_count: int
    setback_front_ft: float
    setback_side_ft: float
    setback_rear_ft: float
    municipality: str = ""


class BuildingViewImage(BaseModel):
    view: str  # "front", "aerial", "side"
    image_base64: str
    prompt_used: str


class BuildingRenderResponse(BaseModel):
    views: list[BuildingViewImage]
    cached: bool
    generation_time_ms: int


# ---------------------------------------------------------------------------
# In-memory LRU cache (max 100 entries, keyed by rounded dimensions)
# ---------------------------------------------------------------------------

_MAX_CACHE = 100
# key → list of (view, base64, prompt)
_cache: OrderedDict[str, list[tuple[str, str, str]]] = OrderedDict()


def _cache_key(req: BuildingRenderRequest) -> str:
    """Deterministic cache key from rounded dimensions."""
    raw = (
        f"{req.property_type}|{req.stories}|"
        f"{round(req.total_width_ft, -1)}|{round(req.total_depth_ft, -1)}|"
        f"{round(req.max_height_ft, -1)}|{req.zoning_district}|{req.unit_count}"
    )
    return hashlib.md5(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_STYLE_BY_TYPE: dict[str, str] = {
    "single_family": "single-family residence",
    "duplex": "side-by-side duplex",
    "multifamily": "multifamily apartment building",
    "commercial_mf": "large multifamily residential complex",
    "commercial": "commercial retail/office building",
    "land": "vacant residential lot",
}

_CAMERA_BY_VIEW: dict[str, str] = {
    "front": (
        "Camera angle: straight-on front elevation view from the street at eye level, "
        "centered on the front facade, showing the full width of the building."
    ),
    "aerial": (
        "Camera angle: elevated 3D aerial view from approximately 45 degrees above "
        "and in front of the building, showing the roof, front facade, and one side, "
        "with the full lot and landscaping visible."
    ),
    "side": (
        "Camera angle: side elevation view from the left side of the building at eye level, "
        "showing the full depth and height of the structure, including the side yard."
    ),
}


def _room_program(req: BuildingRenderRequest) -> str:
    """Generate a detailed architectural program description based on property type."""
    pt = req.property_type
    stories = req.stories
    w = req.total_width_ft
    d = req.total_depth_ft

    if pt == "land":
        return (
            f"Show the empty {req.lot_width_ft:.0f} x {req.lot_depth_ft:.0f} ft lot with "
            f"wooden survey stakes at each corner, a 'For Development' sign near the street, "
            f"wild grass, and dotted lines marking the buildable envelope "
            f"({w:.0f} x {d:.0f} ft) inset from the lot edges by the setbacks: "
            f"{req.setback_front_ft:.0f} ft front, {req.setback_side_ft:.0f} ft sides, "
            f"{req.setback_rear_ft:.0f} ft rear."
        )

    if pt == "single_family":
        beds = 3 if w * d >= 1200 else 2
        garage = "attached two-car garage on the left side" if w >= 35 else "single-car carport"
        if stories >= 2:
            return (
                f"Ground floor: covered front porch with columns spanning the full width, "
                f"a foyer entry, {garage}, open-concept kitchen with island and dining area, "
                f"living room with large windows, half-bath/powder room, laundry room, "
                f"pantry, storage closet, and a screened rear porch. "
                f"Upper floor: master suite with walk-in closet and en-suite bathroom "
                f"(double vanity, soaking tub, separate shower), "
                f"{'bedroom 2 and bedroom 3 each with closets' if beds >= 3 else 'bedroom 2 with closet'}, "
                f"and a shared hall bathroom."
            )
        return (
            f"Single-story layout: covered front porch, foyer entry, {garage}, "
            f"open kitchen with pantry, dining area, living room, "
            f"master suite with walk-in closet and en-suite bath, "
            f"{'bedrooms 2 and 3' if beds >= 3 else 'bedroom 2'}, "
            f"hall bath, powder room, laundry, storage, and screened rear porch."
        )

    if pt == "duplex":
        return (
            f"Side-by-side duplex with a shared center wall dividing two mirror-image units. "
            f"Each unit ({w / 2:.0f} ft wide) has its own front entrance, "
            f"individual driveway, living room at the front, "
            f"kitchen and dining in the middle, "
            f"one bedroom and full bathroom at the rear. "
            f"{'Upper floor adds a second bedroom and bath per unit.' if stories >= 2 else ''}"
        )

    if pt in ("multifamily", "commercial_mf"):
        units_per_floor = max(1, req.unit_count // max(stories, 1))
        return (
            f"Central double-loaded corridor with units on both sides. "
            f"{req.unit_count} total dwelling units across {stories} floors "
            f"(~{units_per_floor} units per floor). Each unit has a living/kitchen area, "
            f"one bedroom, and one bathroom. "
            f"Ground floor: main lobby entrance, mailboxes, and covered parking beneath. "
            f"{'Stairwell and elevator core at the rear of the corridor.' if stories >= 3 else 'Stairwell at the rear.'} "
            f"Upper floors have exterior walkway corridors with metal railings "
            f"and private balconies on each unit."
        )

    # commercial
    return (
        f"Open floor plate commercial space with a glass storefront facade. "
        f"Ground floor: lobby entrance, open retail/office area "
        f"({w:.0f} x {d:.0f} ft clear span), "
        f"restroom core at the rear center, mechanical room in the back corner. "
        f"{'Upper floors: open office layout with stairwell core.' if stories > 1 else ''} "
        f"Prominent signage band above the storefront. "
        f"Surface parking lot in front with ADA-compliant spaces."
    )


def build_architectural_prompt(req: BuildingRenderRequest, view: str = "front") -> str:
    """Construct a detailed architectural rendering prompt from structured data."""
    style = _STYLE_BY_TYPE.get(req.property_type, _STYLE_BY_TYPE["single_family"])
    stories_label = f"{req.stories}-story" if req.stories > 1 else "single-story"

    municipality_note = ""
    if req.municipality:
        municipality_note = f" in {req.municipality}, Florida"

    # Core description
    prompt = (
        f"Photorealistic architectural rendering of a {stories_label} {style}{municipality_note}. "
    )

    # Precise dimensions and lot context
    prompt += (
        f"Building footprint: {req.total_width_ft:.0f} ft wide x {req.total_depth_ft:.0f} ft deep, "
        f"{req.max_height_ft:.0f} ft tall ({req.stories} stories at ~{req.max_height_ft / max(req.stories, 1):.0f} ft each). "
        f"Lot: {req.lot_width_ft:.0f} x {req.lot_depth_ft:.0f} ft. "
        f"Setbacks visible as landscaped yard: "
        f"{req.setback_front_ft:.0f} ft front yard, "
        f"{req.setback_side_ft:.0f} ft side yards, "
        f"{req.setback_rear_ft:.0f} ft rear yard. "
    )

    if req.unit_count > 1:
        prompt += f"The building contains {req.unit_count} dwelling units. "

    # Detailed room program
    prompt += _room_program(req) + " "

    # Regional architectural style
    if req.property_type == "land":
        prompt += (
            "Show neighboring South Florida houses in the background for context. "
            "Tropical vegetation: royal palm trees, saw palmetto, sea grape hedges. "
        )
    elif req.property_type == "commercial":
        prompt += (
            "Modern commercial construction: tilt-up concrete or CMU walls, "
            "flat roof with parapet and rooftop HVAC units, "
            "full-height storefront glazing with aluminum frames, "
            "concrete sidewalk with planters, LED parking lot lights. "
        )
    elif req.property_type in ("multifamily", "commercial_mf"):
        prompt += (
            "South Florida multifamily style: painted CBS (concrete block and stucco) walls, "
            "flat roof with parapet and standing-seam metal accents, "
            "impact-rated aluminum sliding glass doors to balconies, "
            "decorative metal railings, ground-floor covered parking with columns, "
            "tropical landscaping: royal palm trees, bird of paradise, bougainvillea hedges, "
            "concrete driveways, exterior stairwells with metal treads. "
        )
    else:
        prompt += (
            "South Florida residential style: painted stucco exterior walls (warm white or cream), "
            "clay barrel tile roof (terracotta color), impact-rated hurricane windows "
            "with colonial-style shutters, covered entry with decorative columns, "
            "concrete tile driveway, bermuda grass lawn, "
            "tropical landscaping: royal palm trees, bird of paradise, croton shrubs, "
            "decorative river rock beds along the foundation. "
        )

    # Camera angle
    camera = _CAMERA_BY_VIEW.get(view, _CAMERA_BY_VIEW["front"])
    prompt += f"{camera} "

    # Lighting and quality
    prompt += (
        "Lighting: warm late-afternoon golden hour sunlight casting soft shadows, "
        "blue sky with scattered cumulus clouds. "
        "Quality: high-resolution photorealistic architectural visualization, "
        "professional real estate marketing photography, shallow depth of field, "
        "no watermarks, no text overlays, no people."
    )

    return prompt


# ---------------------------------------------------------------------------
# Gemini image generation
# ---------------------------------------------------------------------------


async def generate_building_image(prompt: str) -> str:
    """Call Gemini image generation API, return base64 PNG."""
    from google import genai

    client = genai.Client(api_key=settings.google_api_key)
    response = client.models.generate_content(
        model="gemini-3-pro-image-preview",
        contents=prompt,
        config=genai.types.GenerateContentConfig(
            response_modalities=["IMAGE", "TEXT"],
            image_config=genai.types.ImageConfig(
                aspect_ratio="16:9",
                image_size="2K",
            ),
        ),
    )

    # Extract image from response
    for part in response.candidates[0].content.parts:
        if part.inline_data is not None:
            return base64.b64encode(part.inline_data.data).decode("utf-8")

    raise ValueError("Gemini response contained no image data")


_VIEWS = ["front", "aerial", "side"]


# ---------------------------------------------------------------------------
# Route
# ---------------------------------------------------------------------------


@router.post("/building", response_model=BuildingRenderResponse)
async def render_building(request: BuildingRenderRequest) -> BuildingRenderResponse:
    """Generate AI architectural renderings (front, aerial, side) from zoning parameters."""
    if not settings.google_api_key:
        raise HTTPException(
            status_code=503,
            detail="Building rendering unavailable — GOOGLE_API_KEY not configured",
        )

    key = _cache_key(request)

    # Check cache
    if key in _cache:
        cached_views = _cache[key]
        _cache.move_to_end(key)
        logger.info("Building render cache hit: %s", key[:8])
        return BuildingRenderResponse(
            views=[
                BuildingViewImage(view=v, image_base64=b64, prompt_used=p)
                for v, b64, p in cached_views
            ],
            cached=True,
            generation_time_ms=0,
        )

    # Build prompts for all 3 views
    prompts = {view: build_architectural_prompt(request, view) for view in _VIEWS}

    t0 = time.monotonic()
    try:
        # Generate all 3 views concurrently
        results = await asyncio.gather(
            *(generate_building_image(prompts[view]) for view in _VIEWS),
            return_exceptions=True,
        )
    except Exception as e:
        logger.error("Gemini image generation failed: %s", e)
        raise HTTPException(
            status_code=502,
            detail=f"Image generation failed: {type(e).__name__}: {e}",
        ) from e
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    # Build response, skipping any individual failures
    view_images: list[BuildingViewImage] = []
    cache_entries: list[tuple[str, str, str]] = []
    for view, result in zip(_VIEWS, results):
        if isinstance(result, Exception):
            logger.warning("View '%s' generation failed: %s", view, result)
            continue
        view_images.append(
            BuildingViewImage(view=view, image_base64=result, prompt_used=prompts[view])
        )
        cache_entries.append((view, result, prompts[view]))

    if not view_images:
        raise HTTPException(
            status_code=502,
            detail="All image generations failed",
        )

    # Store in cache
    _cache[key] = cache_entries
    if len(_cache) > _MAX_CACHE:
        _cache.popitem(last=False)

    logger.info(
        "Building render: %d/%d views in %dms: %s",
        len(view_images),
        len(_VIEWS),
        elapsed_ms,
        key[:8],
    )

    return BuildingRenderResponse(
        views=view_images,
        cached=False,
        generation_time_ms=elapsed_ms,
    )
