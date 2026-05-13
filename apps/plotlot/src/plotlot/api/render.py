"""Building render endpoint — local architectural visualizations.

Uses deterministic server-local PNG generation to produce schematic renderings
from structured zoning/floor plan data, replacing hosted image-generation APIs.
Generates three views: front, aerial 3D, and side.
"""

import base64
import hashlib
import logging
import random
import struct
import time
import zlib
from collections import OrderedDict

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

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
        f"Ultra-realistic architectural visualization of a {stories_label} {style}{municipality_note}. "
        f"Photorealistic rendering, magazine-quality real estate photography style. "
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
        "Lighting: warm late-afternoon golden hour sunlight casting soft long shadows, "
        "blue sky with scattered cumulus clouds, warm amber light on the facade. "
        "Quality: ultra-high-resolution photorealistic architectural visualization, "
        "professional real estate marketing photography, shallow depth of field, "
        "8K detail, no watermarks, no text overlays, no people."
    )

    return prompt


# ---------------------------------------------------------------------------
# Local PNG generation
# ---------------------------------------------------------------------------


async def generate_building_image(prompt: str) -> str:
    """Generate a deterministic local PNG and return it as base64."""

    return base64.b64encode(_render_local_png(prompt)).decode("utf-8")


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + kind
        + data
        + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
    )


def _encode_png(width: int, height: int, pixels: bytearray) -> bytes:
    rows = []
    stride = width * 3
    for y in range(height):
        rows.append(b"\x00" + bytes(pixels[y * stride : (y + 1) * stride]))
    raw = b"".join(rows)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + _png_chunk(b"IDAT", zlib.compress(raw, level=6))
        + _png_chunk(b"IEND", b"")
    )


def _set_pixel(pixels: bytearray, width: int, x: int, y: int, color: tuple[int, int, int]) -> None:
    if x < 0 or y < 0 or x >= width:
        return
    idx = (y * width + x) * 3
    if idx < 0 or idx + 2 >= len(pixels):
        return
    pixels[idx : idx + 3] = bytes(color)


def _rect(
    pixels: bytearray,
    width: int,
    height: int,
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    color: tuple[int, int, int],
) -> None:
    for y in range(max(0, y0), min(height, y1)):
        row_start = (y * width + max(0, x0)) * 3
        row_end = (y * width + min(width, x1)) * 3
        pixels[row_start:row_end] = bytes(color) * max(0, min(width, x1) - max(0, x0))


def _render_local_png(prompt: str) -> bytes:
    """Render a simple schematic building concept as a PNG."""

    width, height = 1024, 576
    seed = int(hashlib.md5(prompt.encode()).hexdigest()[:8], 16)
    rng = random.Random(seed)
    pixels = bytearray(width * height * 3)

    # Sky/ground gradient.
    for y in range(height):
        if y < 380:
            t = y / 380
            color = (
                int(246 - 70 * t),
                int(222 - 45 * t),
                int(170 + 35 * t),
            )
        else:
            t = (y - 380) / max(height - 380, 1)
            color = (
                int(86 - 25 * t),
                int(128 - 20 * t),
                int(82 - 18 * t),
            )
        _rect(pixels, width, height, 0, y, width, y + 1, color)

    # Lot pad and building mass.
    _rect(pixels, width, height, 120, 390, 904, 500, (198, 181, 149))
    bx0 = 250 + rng.randint(-40, 40)
    bx1 = 780 + rng.randint(-35, 35)
    by0 = 180 + rng.randint(-25, 20)
    by1 = 398
    facade = rng.choice([(232, 220, 198), (214, 205, 188), (226, 218, 204)])
    shadow = (
        max(0, facade[0] - 38),
        max(0, facade[1] - 38),
        max(0, facade[2] - 38),
    )
    trim = (86, 74, 63)
    roof = rng.choice([(149, 79, 54), (84, 72, 62), (105, 87, 66)])

    if "aerial" in prompt.lower():
        _rect(pixels, width, height, bx0 - 35, by0 + 35, bx1 - 35, by1 + 25, shadow)
        _rect(pixels, width, height, bx0, by0, bx1, by1, facade)
        _rect(pixels, width, height, bx0 - 20, by0 - 22, bx1 + 20, by0 + 12, roof)
        for offset in range(0, bx1 - bx0, 72):
            _rect(pixels, width, height, bx0 + offset + 12, by0 + 42, bx0 + offset + 44, by1 - 30, (113, 137, 148))
    else:
        _rect(pixels, width, height, bx0, by0, bx1, by1, facade)
        _rect(pixels, width, height, bx0 - 28, by0 - 30, bx1 + 28, by0, roof)
        _rect(pixels, width, height, bx0, by1 - 15, bx1, by1, trim)
        floors = 3 if "multifamily" in prompt.lower() or "3 stories" in prompt.lower() else 2
        cols = 7 if bx1 - bx0 > 480 else 5
        for floor in range(floors):
            wy = by0 + 38 + floor * max(48, (by1 - by0 - 75) // floors)
            for col in range(cols):
                wx = bx0 + 36 + col * ((bx1 - bx0 - 72) // max(cols - 1, 1))
                _rect(pixels, width, height, wx, wy, wx + 38, wy + 30, (89, 124, 142))
                _rect(pixels, width, height, wx + 4, wy + 4, wx + 34, wy + 26, (158, 188, 199))
        _rect(pixels, width, height, (bx0 + bx1) // 2 - 28, by1 - 84, (bx0 + bx1) // 2 + 28, by1, (85, 67, 52))

    # Simple palms/landscaping.
    for x in (165, 850, 210, 810):
        trunk_top = 280 + rng.randint(-30, 20)
        _rect(pixels, width, height, x, trunk_top, x + 10, 455, (112, 74, 45))
        for dx, dy in ((-38, 0), (-24, -18), (0, -28), (24, -18), (38, 0)):
            _rect(pixels, width, height, x + dx, trunk_top + dy, x + dx + 44, trunk_top + dy + 10, (47, 106, 66))

    # Drive/walkway.
    _rect(pixels, width, height, width // 2 - 45, by1, width // 2 + 45, height, (188, 184, 174))
    _rect(pixels, width, height, 0, 505, width, height, (70, 70, 68))
    return _encode_png(width, height, pixels)


_VIEWS = ["front", "aerial", "side"]


# ---------------------------------------------------------------------------
# Development concept endpoint — request/response models + cache
# ---------------------------------------------------------------------------


class ConceptRenderRequest(BaseModel):
    address: str
    municipality: str
    zoning_district: str
    property_type: str  # multifamily, mixed_use, townhome, commercial_mf, single_family
    max_units: int
    lot_sqft: float


class ConceptRenderResponse(BaseModel):
    image_base64: str
    prompt_used: str
    cached: bool


_concept_cache: OrderedDict[str, tuple[str, str]] = OrderedDict()

_CONCEPT_TYPE_LABELS: dict[str, str] = {
    "multifamily": "multifamily residential",
    "commercial_mf": "large multifamily residential complex",
    "mixed_use": "mixed-use residential and retail",
    "townhome": "townhome",
    "single_family": "single-family",
    "commercial": "commercial",
    "land": "residential",
}


def build_concept_prompt(req: ConceptRenderRequest) -> str:
    """Build a development concept visualization prompt."""
    label = _CONCEPT_TYPE_LABELS.get(req.property_type, req.property_type.replace("_", " "))
    lot_acres = req.lot_sqft / 43560

    return (
        f"Photorealistic architectural rendering of a completed {req.max_units}-unit {label} "
        f"development at {req.address}, {req.municipality}. "
        f"South Florida {req.municipality} architectural style, "
        f"finished professional landscaping with tropical royal palm trees, "
        f"mature bougainvillea hedges, paved walkways, and manicured bermuda grass lawns. "
        f"Street-level perspective from the public sidewalk, showing the full building frontage. "
        f"The {lot_acres:.2f}-acre site is fully developed with the completed {req.zoning_district} project. "
        f"Golden hour lighting with warm amber and rose sky at dusk, "
        f"soft long shadows across the landscaped grounds. "
        f"Ultra-realistic visualization quality, magazine-quality real estate development marketing. "
        f"No people, no watermarks, no text overlays."
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.post("/building", response_model=BuildingRenderResponse)
async def render_building(request: BuildingRenderRequest) -> BuildingRenderResponse:
    """Generate local architectural renderings (front, aerial, side) from zoning parameters."""

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
    results: list[str | Exception] = []
    for view in _VIEWS:
        try:
            results.append(await generate_building_image(prompts[view]))
        except Exception as e:
            logger.warning("Local view '%s' generation failed: %s", view, e)
            results.append(e)
    elapsed_ms = int((time.monotonic() - t0) * 1000)

    # Build response, skipping any individual failures
    view_images: list[BuildingViewImage] = []
    cache_entries: list[tuple[str, str, str]] = []
    for view, result in zip(_VIEWS, results):
        if isinstance(result, Exception):
            logger.warning("View '%s' generation failed: %s", view, result)
            continue
        # Type narrowing: result is str at this point (Exception cases already skipped)
        image_b64: str = result  # type: ignore[assignment]
        view_images.append(
            BuildingViewImage(view=view, image_base64=image_b64, prompt_used=prompts[view])
        )
        cache_entries.append((view, image_b64, prompts[view]))

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


@router.post("/concept", response_model=ConceptRenderResponse)
async def render_concept(request: ConceptRenderRequest) -> ConceptRenderResponse:
    """Generate a development concept visualization for a completed build-out."""
    cache_key = hashlib.md5(
        f"{request.address}|{request.property_type}|{request.max_units}".encode()
    ).hexdigest()

    if cache_key in _concept_cache:
        _concept_cache.move_to_end(cache_key)
        b64, prompt = _concept_cache[cache_key]
        logger.info("Concept render cache hit: %s", cache_key[:8])
        return ConceptRenderResponse(image_base64=b64, prompt_used=prompt, cached=True)

    prompt = build_concept_prompt(request)
    t0 = time.monotonic()

    try:
        image_b64 = await generate_building_image(prompt)
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e)) from e

    elapsed_ms = int((time.monotonic() - t0) * 1000)

    _concept_cache[cache_key] = (image_b64, prompt)
    if len(_concept_cache) > _MAX_CACHE:
        _concept_cache.popitem(last=False)

    logger.info("Concept render: %dms: %s", elapsed_ms, cache_key[:8])
    return ConceptRenderResponse(image_base64=image_b64, prompt_used=prompt, cached=False)
