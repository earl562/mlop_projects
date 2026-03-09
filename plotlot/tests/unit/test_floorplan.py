"""Tests for parametric floor plan generator."""

import pytest

from plotlot.rendering.floorplan import (
    FloorPlan,
    FloorPlanRequest,
    UnitLayout,
    floor_plan_to_svg,
    generate_floor_plan,
)


class TestSingleFamily:
    """Single-family template generation."""

    def test_basic_dimensions(self):
        req = FloorPlanRequest(buildable_width_ft=50, buildable_depth_ft=80)
        plan = generate_floor_plan(req)

        assert plan.template == "single_family"
        assert plan.total_units == 1
        assert len(plan.units) == 1
        assert plan.units[0].unit_id == "A1"
        assert plan.units[0].width_ft == 50
        assert plan.units[0].depth_ft == 80

    def test_stories_from_height(self):
        req = FloorPlanRequest(
            buildable_width_ft=40,
            buildable_depth_ft=60,
            max_height_ft=25.0,
            story_height_ft=10.0,
        )
        plan = generate_floor_plan(req)

        # 25/10 = 2 stories (capped at 2 for SFH)
        assert plan.stories == 2
        # Area includes both stories
        assert plan.units[0].area_sqft == 40 * 60 * 2

    def test_sfh_capped_at_two_stories(self):
        req = FloorPlanRequest(
            buildable_width_ft=40,
            buildable_depth_ft=60,
            max_height_ft=50.0,
            story_height_ft=10.0,
        )
        plan = generate_floor_plan(req)
        assert plan.stories == 2  # capped even though height allows 5

    def test_parking_minimum_two(self):
        req = FloorPlanRequest(
            buildable_width_ft=40,
            buildable_depth_ft=60,
            parking_per_unit=1.0,
        )
        plan = generate_floor_plan(req)
        assert plan.parking_spaces >= 2


class TestDuplex:
    """Duplex template generation."""

    def test_side_by_side_wide_lot(self):
        req = FloorPlanRequest(
            buildable_width_ft=50,
            buildable_depth_ft=80,
            max_units=2,
        )
        plan = generate_floor_plan(req)

        assert plan.template == "duplex"
        assert plan.total_units == 2
        assert len(plan.units) == 2
        assert "side-by-side" in plan.notes[0]

    def test_stacked_narrow_lot_two_stories(self):
        req = FloorPlanRequest(
            buildable_width_ft=25,
            buildable_depth_ft=60,
            max_height_ft=25.0,
            max_units=2,
        )
        plan = generate_floor_plan(req)

        assert plan.template == "duplex"
        assert plan.total_units == 2
        assert "stacked" in plan.notes[0]
        assert plan.units[0].floor == 1
        assert plan.units[1].floor == 2

    def test_front_back_narrow_lot_one_story(self):
        req = FloorPlanRequest(
            buildable_width_ft=25,
            buildable_depth_ft=60,
            max_height_ft=9.0,  # only 1 story possible
            max_units=2,
        )
        plan = generate_floor_plan(req)

        assert plan.template == "duplex"
        assert "front-back" in plan.notes[0]
        assert plan.units[0].floor == 1
        assert plan.units[1].floor == 1

    def test_duplex_parking(self):
        req = FloorPlanRequest(
            buildable_width_ft=50,
            buildable_depth_ft=80,
            max_units=2,
            parking_per_unit=1.5,
        )
        plan = generate_floor_plan(req)
        assert plan.parking_spaces == 3  # int(1.5 * 2)


class TestSmallMultifamily:
    """Small multifamily template generation."""

    def test_four_units(self):
        req = FloorPlanRequest(
            buildable_width_ft=60,
            buildable_depth_ft=80,
            max_height_ft=35.0,
            max_units=4,
        )
        plan = generate_floor_plan(req)

        assert plan.template == "small_multifamily"
        assert plan.total_units <= 4
        assert len(plan.units) == plan.total_units
        assert plan.stories <= 3

    def test_corridor_layout_notes(self):
        req = FloorPlanRequest(
            buildable_width_ft=60,
            buildable_depth_ft=80,
            max_units=6,
        )
        plan = generate_floor_plan(req)

        assert any("loaded corridor" in n for n in plan.notes)
        assert any("stories" in n for n in plan.notes)
        assert any("Unit size" in n for n in plan.notes)

    def test_max_three_stories(self):
        req = FloorPlanRequest(
            buildable_width_ft=60,
            buildable_depth_ft=80,
            max_height_ft=100.0,
            max_units=8,
        )
        plan = generate_floor_plan(req)
        assert plan.stories <= 3


class TestAutoTemplateSelection:
    """Auto template selection based on max_units."""

    def test_auto_single_family(self):
        req = FloorPlanRequest(
            buildable_width_ft=50,
            buildable_depth_ft=80,
            max_units=1,
            template="auto",
        )
        plan = generate_floor_plan(req)
        assert plan.template == "single_family"

    def test_auto_duplex(self):
        req = FloorPlanRequest(
            buildable_width_ft=50,
            buildable_depth_ft=80,
            max_units=2,
            template="auto",
        )
        plan = generate_floor_plan(req)
        assert plan.template == "duplex"

    def test_auto_multifamily(self):
        req = FloorPlanRequest(
            buildable_width_ft=60,
            buildable_depth_ft=80,
            max_units=4,
            template="auto",
        )
        plan = generate_floor_plan(req)
        assert plan.template == "small_multifamily"

    def test_explicit_template_overrides_auto(self):
        req = FloorPlanRequest(
            buildable_width_ft=60,
            buildable_depth_ft=80,
            max_units=4,
            template="single_family",
        )
        plan = generate_floor_plan(req)
        assert plan.template == "single_family"


class TestMinUnitSizeWarning:
    """Min unit size warning generation."""

    def test_duplex_min_size_warning(self):
        req = FloorPlanRequest(
            buildable_width_ft=30,
            buildable_depth_ft=20,
            max_units=2,
            min_unit_size_sqft=400.0,
        )
        plan = generate_floor_plan(req)

        # With 30ft width, each side-by-side unit is ~14.5 x 20 = 290 sqft
        warnings = [n for n in plan.notes if "Warning" in n]
        assert len(warnings) > 0
        assert "below min" in warnings[0]

    def test_multifamily_min_size_warning(self):
        req = FloorPlanRequest(
            buildable_width_ft=30,
            buildable_depth_ft=30,
            max_units=6,
            min_unit_size_sqft=500.0,
        )
        plan = generate_floor_plan(req)

        # Check if any units are too small (depends on layout)
        has_small_unit = any(u.area_sqft < 500.0 for u in plan.units)
        if has_small_unit:
            warnings = [n for n in plan.notes if "Warning" in n]
            assert len(warnings) > 0


class TestSVGOutput:
    """SVG rendering output."""

    def test_svg_contains_expected_elements(self):
        req = FloorPlanRequest(
            buildable_width_ft=50,
            buildable_depth_ft=80,
            max_units=1,
        )
        plan = generate_floor_plan(req)
        svg = floor_plan_to_svg(plan)

        assert "<svg" in svg
        assert "</svg>" in svg
        assert 'class="lot"' in svg
        assert 'class="unit"' in svg
        assert 'class="unit-label"' in svg
        assert "Unit A1" in svg
        assert "50 ft" in svg
        assert "80 ft" in svg

    def test_svg_duplex_has_two_unit_rects(self):
        req = FloorPlanRequest(
            buildable_width_ft=50,
            buildable_depth_ft=80,
            max_units=2,
        )
        plan = generate_floor_plan(req)
        svg = floor_plan_to_svg(plan)

        assert "Unit A" in svg
        assert "Unit B" in svg

    def test_svg_respects_scale(self):
        req = FloorPlanRequest(buildable_width_ft=50, buildable_depth_ft=80)
        plan = generate_floor_plan(req)

        svg_default = floor_plan_to_svg(plan, scale=4.0)
        svg_large = floor_plan_to_svg(plan, scale=8.0)

        # Larger scale = bigger SVG
        assert 'width="280"' in svg_default  # 50*4 + 2*40
        assert 'width="480"' in svg_large  # 50*8 + 2*40

    def test_svg_title_contains_template(self):
        req = FloorPlanRequest(
            buildable_width_ft=50,
            buildable_depth_ft=80,
            max_units=2,
        )
        plan = generate_floor_plan(req)
        svg = floor_plan_to_svg(plan)

        assert "Duplex" in svg


class TestEdgeCases:
    """Edge cases and error handling."""

    def test_very_small_lot(self):
        req = FloorPlanRequest(
            buildable_width_ft=10,
            buildable_depth_ft=10,
            max_units=1,
        )
        plan = generate_floor_plan(req)
        assert plan.total_units == 1
        assert plan.units[0].area_sqft > 0

    def test_unknown_template_raises(self):
        req = FloorPlanRequest(
            buildable_width_ft=50,
            buildable_depth_ft=80,
            template="mansion",
        )
        with pytest.raises(ValueError, match="Unknown template"):
            generate_floor_plan(req)

    def test_all_units_have_valid_polygons(self):
        """Every generated unit must have a Shapely polygon with positive area."""
        for max_units in [1, 2, 4, 8]:
            req = FloorPlanRequest(
                buildable_width_ft=60,
                buildable_depth_ft=80,
                max_height_ft=35.0,
                max_units=max_units,
            )
            plan = generate_floor_plan(req)

            for unit in plan.units:
                assert unit.polygon.is_valid, f"{unit.unit_id} polygon is invalid"
                assert unit.polygon.area > 0, f"{unit.unit_id} polygon has zero area"
                assert unit.area_sqft > 0, f"{unit.unit_id} area_sqft is zero"

    def test_narrow_lot_multifamily_single_loaded(self):
        """Narrow lots should fall back to single-loaded corridor."""
        req = FloorPlanRequest(
            buildable_width_ft=25,
            buildable_depth_ft=80,
            max_units=4,
        )
        plan = generate_floor_plan(req)
        assert plan.template == "small_multifamily"
        assert any("single-loaded" in n for n in plan.notes)
