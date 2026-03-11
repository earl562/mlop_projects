/**
 * Client-side architectural floor plan generator driven by zoning constraints.
 *
 * The floor plan shows what the developer is *legally allowed to build* on a
 * specific lot, not a generic template. Every dimension is constrained by the
 * zoning report's numeric parameters.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FloorPlanInput {
  buildableWidthFt: number;
  buildableDepthFt: number;
  maxHeightFt: number;
  maxStories: number;
  maxLotCoveragePct: number;
  far: number;
  maxUnits: number;
  minUnitSizeSqft: number;
  parkingPerUnit: number;
  lotSizeSqft: number;
  propertyType: string;
}

export type RoomType =
  | "living"
  | "kitchen"
  | "dining"
  | "bedroom"
  | "bathroom"
  | "garage"
  | "laundry"
  | "entry"
  | "hallway"
  | "closet"
  | "corridor"
  | "stairwell"
  | "mechanical"
  | "lobby"
  | "open_floor";

export interface Room {
  name: string;
  x: number;
  y: number;
  width: number;
  depth: number;
  floor: number;
  type: RoomType;
  isWetRoom: boolean;
}

export interface Door {
  x: number;
  y: number;
  wall: "north" | "south" | "east" | "west";
  width: number;
  isExterior: boolean;
}

export interface Window {
  x: number;
  y: number;
  wall: "north" | "south" | "east" | "west";
  width: number;
}

export interface FloorPlanLayout {
  rooms: Room[];
  doors: Door[];
  windows: Window[];
  dimensions: { totalWidth: number; totalDepth: number };
  template: string;
  stories: number;
  footprintSqft: number;
  totalFloorAreaSqft: number;
  maxAllowedFloorArea: number;
  lotCoverageUsedPct: number;
  lotCoverageAllowedPct: number;
  unitCount: number;
  minUnitSizeSqft: number;
  complianceNotes: string[];
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function clamp(val: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, val));
}

function computeEffectiveFootprint(input: FloorPlanInput): {
  width: number;
  depth: number;
  footprintSqft: number;
} {
  const { buildableWidthFt, buildableDepthFt, maxLotCoveragePct, lotSizeSqft } = input;
  const buildable = buildableWidthFt * buildableDepthFt;
  const coverageLimit =
    maxLotCoveragePct > 0 ? (maxLotCoveragePct / 100) * lotSizeSqft : Infinity;
  const footprintSqft = Math.min(buildable, coverageLimit);

  if (footprintSqft >= buildable) {
    return { width: buildableWidthFt, depth: buildableDepthFt, footprintSqft: buildable };
  }

  // Scale down proportionally
  const scale = Math.sqrt(footprintSqft / buildable);
  const w = buildableWidthFt * scale;
  const d = buildableDepthFt * scale;
  return { width: w, depth: d, footprintSqft: w * d };
}

function computeStories(input: FloorPlanInput): number {
  const fromHeight = Math.floor(input.maxHeightFt / 10);
  return Math.max(1, Math.min(input.maxStories || fromHeight, fromHeight));
}

// ---------------------------------------------------------------------------
// Single-family layout
// ---------------------------------------------------------------------------

function generateSingleFamily(input: FloorPlanInput): FloorPlanLayout {
  const { width, depth, footprintSqft } = computeEffectiveFootprint(input);
  const stories = computeStories(input);
  const farLimit = input.far > 0 ? input.far * input.lotSizeSqft : Infinity;
  const totalFloorArea = Math.min(footprintSqft * stories, farLimit);
  const floorArea = totalFloorArea / stories;

  const rooms: Room[] = [];
  const doors: Door[] = [];
  const windows: Window[] = [];

  // Room allocation percentages (of total floor area)
  const hasGarage = input.parkingPerUnit >= 1.5;
  const garageW = hasGarage ? clamp(width * 0.35, 16, 24) : 0;
  const garageD = hasGarage ? clamp(depth * 0.3, 18, 24) : 0;
  const hasBed3 = totalFloorArea >= 1200;

  if (stories >= 2) {
    // ── Two-story layout ──
    // Ground floor: garage, living, kitchen, dining, laundry, half bath, entry
    const groundArea = floorArea;
    const rightW = width - garageW;

    // Garage (front-left)
    if (hasGarage) {
      rooms.push({
        name: "2-Car Garage",
        x: 0, y: 0,
        width: garageW, depth: garageD,
        floor: 1, type: "garage", isWetRoom: false,
      });
      // Garage door
      doors.push({ x: garageW / 2, y: 0, wall: "south", width: 16, isExterior: true });
    }

    // Entry / Foyer (front-right)
    const entryW = clamp(rightW * 0.3, 6, 10);
    const entryD = clamp(depth * 0.15, 5, 8);
    rooms.push({
      name: "Entry",
      x: garageW, y: 0,
      width: entryW, depth: entryD,
      floor: 1, type: "entry", isWetRoom: false,
    });
    doors.push({ x: garageW + entryW / 2, y: 0, wall: "south", width: 3, isExterior: true });

    // Living Room (front-right, next to entry)
    const livingW = rightW - entryW;
    const livingD = clamp(depth * 0.4, 12, 18);
    rooms.push({
      name: "Living Room",
      x: garageW + entryW, y: 0,
      width: livingW, depth: livingD,
      floor: 1, type: "living", isWetRoom: false,
    });
    windows.push({ x: garageW + entryW + livingW / 2, y: 0, wall: "south", width: 4 });

    // Kitchen (back-left, behind garage)
    const kitchenW = clamp(width * 0.4, 10, 16);
    const kitchenD = clamp(depth * 0.3, 10, 14);
    const kitchenY = Math.max(garageD, livingD);
    rooms.push({
      name: "Kitchen",
      x: 0, y: kitchenY,
      width: kitchenW, depth: kitchenD,
      floor: 1, type: "kitchen", isWetRoom: true,
    });
    doors.push({ x: kitchenW, y: kitchenY + kitchenD / 2, wall: "east", width: 3, isExterior: false });

    // Dining (back-right, adjacent to kitchen)
    const diningW = width - kitchenW;
    const diningD = kitchenD;
    rooms.push({
      name: "Dining",
      x: kitchenW, y: kitchenY,
      width: diningW, depth: diningD,
      floor: 1, type: "dining", isWetRoom: false,
    });

    // Laundry (behind garage, small)
    const laundryW = clamp(garageW * 0.5, 5, 8);
    const laundryD = clamp(depth * 0.1, 4, 6);
    const laundryY = kitchenY + kitchenD;
    if (laundryY + laundryD <= depth) {
      rooms.push({
        name: "Laundry",
        x: 0, y: laundryY,
        width: laundryW, depth: laundryD,
        floor: 1, type: "laundry", isWetRoom: true,
      });
    }

    // Half Bath (ground floor)
    const halfBathW = clamp(width * 0.1, 4, 6);
    const halfBathD = clamp(depth * 0.08, 4, 5);
    rooms.push({
      name: "Half Bath",
      x: laundryW, y: laundryY,
      width: halfBathW, depth: halfBathD,
      floor: 1, type: "bathroom", isWetRoom: true,
    });

    // Upper floor: master suite + bath, bedrooms, hall bath
    const masterW = clamp(width * 0.45, 12, 18);
    const masterD = clamp(depth * 0.45, 12, 16);
    rooms.push({
      name: "Master Suite",
      x: 0, y: 0,
      width: masterW, depth: masterD,
      floor: 2, type: "bedroom", isWetRoom: false,
    });
    windows.push({ x: masterW / 2, y: 0, wall: "south", width: 4 });

    // Master Bath
    const mbathW = clamp(masterW * 0.5, 6, 10);
    const mbathD = clamp(depth * 0.15, 5, 8);
    rooms.push({
      name: "Master Bath",
      x: 0, y: masterD,
      width: mbathW, depth: mbathD,
      floor: 2, type: "bathroom", isWetRoom: true,
    });
    doors.push({ x: mbathW / 2, y: masterD, wall: "north", width: 2.5, isExterior: false });

    // Bedroom 2
    const bed2W = width - masterW;
    const bed2D = clamp(depth * 0.4, 10, 14);
    rooms.push({
      name: "Bedroom 2",
      x: masterW, y: 0,
      width: bed2W, depth: bed2D,
      floor: 2, type: "bedroom", isWetRoom: false,
    });
    windows.push({ x: masterW + bed2W / 2, y: 0, wall: "south", width: 3 });
    doors.push({ x: masterW, y: bed2D / 2, wall: "west", width: 2.5, isExterior: false });

    // Bedroom 3 (if area allows)
    if (hasBed3) {
      const bed3W = width - masterW;
      const bed3D = clamp(depth * 0.35, 10, 12);
      const bed3Y = bed2D;
      if (bed3Y + bed3D <= depth) {
        rooms.push({
          name: "Bedroom 3",
          x: masterW, y: bed3Y,
          width: bed3W, depth: bed3D,
          floor: 2, type: "bedroom", isWetRoom: false,
        });
        windows.push({ x: masterW + bed3W / 2, y: bed3Y + bed3D, wall: "north", width: 3 });
      }
    }

    // Hall Bath (upper)
    const hbathW = clamp(width * 0.15, 5, 8);
    const hbathD = clamp(depth * 0.12, 5, 7);
    rooms.push({
      name: "Hall Bath",
      x: masterW, y: depth - hbathD,
      width: hbathW, depth: hbathD,
      floor: 2, type: "bathroom", isWetRoom: true,
    });

    // Exterior windows on back wall (north)
    windows.push({ x: width * 0.25, y: depth, wall: "north", width: 3 });
    windows.push({ x: width * 0.75, y: depth, wall: "north", width: 3 });
  } else {
    // ── Single-story layout ──
    // 2-column grid: left column, right column

    const leftColW = hasGarage ? clamp(width * 0.4, 16, 24) : clamp(width * 0.45, 12, 20);
    const rightColW = width - leftColW;

    let leftY = 0;
    let rightY = 0;

    // Garage (front-left)
    if (hasGarage) {
      const gD = clamp(depth * 0.3, 18, 22);
      rooms.push({
        name: "2-Car Garage",
        x: 0, y: 0,
        width: leftColW, depth: gD,
        floor: 1, type: "garage", isWetRoom: false,
      });
      doors.push({ x: leftColW / 2, y: 0, wall: "south", width: 16, isExterior: true });
      leftY = gD;
    }

    // Entry (front-right)
    const entryD = clamp(depth * 0.1, 4, 6);
    rooms.push({
      name: "Entry",
      x: leftColW, y: 0,
      width: rightColW, depth: entryD,
      floor: 1, type: "entry", isWetRoom: false,
    });
    doors.push({ x: leftColW + rightColW / 2, y: 0, wall: "south", width: 3, isExterior: true });
    rightY = entryD;

    // Living Room (right, below entry)
    const livingD = clamp(depth * 0.3, 12, 16);
    rooms.push({
      name: "Living Room",
      x: leftColW, y: rightY,
      width: rightColW, depth: livingD,
      floor: 1, type: "living", isWetRoom: false,
    });
    windows.push({ x: leftColW + rightColW, y: rightY + livingD / 2, wall: "east", width: 4 });
    rightY += livingD;

    // Kitchen (left, below garage)
    const kitchenD = clamp(depth * 0.22, 10, 14);
    rooms.push({
      name: "Kitchen",
      x: 0, y: leftY,
      width: leftColW, depth: kitchenD,
      floor: 1, type: "kitchen", isWetRoom: true,
    });
    doors.push({ x: leftColW, y: leftY + kitchenD / 2, wall: "east", width: 3, isExterior: false });
    leftY += kitchenD;

    // Dining (right, below living)
    const diningD = clamp(depth * 0.15, 8, 12);
    rooms.push({
      name: "Dining",
      x: leftColW, y: rightY,
      width: rightColW, depth: diningD,
      floor: 1, type: "dining", isWetRoom: false,
    });
    rightY += diningD;

    // Laundry (left, small)
    const laundryD = clamp(depth * 0.08, 4, 6);
    rooms.push({
      name: "Laundry",
      x: 0, y: leftY,
      width: clamp(leftColW * 0.5, 5, 8), depth: laundryD,
      floor: 1, type: "laundry", isWetRoom: true,
    });
    leftY += laundryD;

    // Master Suite (back-left)
    const masterD = clamp(depth - leftY, 12, 18);
    rooms.push({
      name: "Master Suite",
      x: 0, y: leftY,
      width: leftColW, depth: masterD,
      floor: 1, type: "bedroom", isWetRoom: false,
    });
    windows.push({ x: 0, y: leftY + masterD / 2, wall: "west", width: 4 });
    doors.push({ x: leftColW, y: leftY + masterD / 2, wall: "east", width: 2.5, isExterior: false });

    // Master Bath (inline)
    const mbathW = clamp(leftColW * 0.4, 6, 10);
    const mbathD = clamp(masterD * 0.35, 5, 8);
    rooms.push({
      name: "Master Bath",
      x: 0, y: leftY + masterD,
      width: mbathW, depth: mbathD,
      floor: 1, type: "bathroom", isWetRoom: true,
    });

    // Bedroom 2 (back-right)
    const bed2D = clamp(depth - rightY, 10, 16);
    const hallBathW = clamp(rightColW * 0.35, 5, 8);
    const bed2W = rightColW - hallBathW;
    rooms.push({
      name: "Bedroom 2",
      x: leftColW, y: rightY,
      width: bed2W, depth: bed2D,
      floor: 1, type: "bedroom", isWetRoom: false,
    });
    windows.push({ x: leftColW + bed2W / 2, y: depth, wall: "north", width: 3 });
    doors.push({ x: leftColW, y: rightY + bed2D / 2, wall: "west", width: 2.5, isExterior: false });

    // Hall Bath (back-right corner)
    const hbathD = clamp(bed2D * 0.5, 5, 8);
    rooms.push({
      name: "Hall Bath",
      x: leftColW + bed2W, y: rightY,
      width: hallBathW, depth: hbathD,
      floor: 1, type: "bathroom", isWetRoom: true,
    });

    // Bedroom 3 (if area allows)
    if (hasBed3 && rightY + bed2D + 10 <= depth) {
      rooms.push({
        name: "Bedroom 3",
        x: leftColW + bed2W, y: rightY + hbathD,
        width: hallBathW, depth: bed2D - hbathD,
        floor: 1, type: "bedroom", isWetRoom: false,
      });
    }

    // Back wall windows
    windows.push({ x: width * 0.25, y: depth, wall: "north", width: 3 });
  }

  // Compliance
  const complianceNotes: string[] = [];
  const lotCoverageUsed = input.lotSizeSqft > 0
    ? (footprintSqft / input.lotSizeSqft) * 100
    : 0;
  const coverageAllowed = input.maxLotCoveragePct || 100;

  if (coverageAllowed < 100) {
    const pctUsed = Math.round((lotCoverageUsed / coverageAllowed) * 100);
    complianceNotes.push(`Lot coverage ${Math.round(lotCoverageUsed)}% of ${coverageAllowed}% max (${pctUsed}% utilized)`);
    if (pctUsed > 90) complianceNotes.push("WARNING: Lot coverage near maximum");
  }

  if (input.far > 0) {
    const farUsed = totalFloorArea / input.lotSizeSqft;
    const pctUsed = Math.round((farUsed / input.far) * 100);
    complianceNotes.push(`FAR ${farUsed.toFixed(2)} of ${input.far.toFixed(2)} max (${pctUsed}% utilized)`);
    if (pctUsed > 90) complianceNotes.push("WARNING: FAR near maximum");
  }

  return {
    rooms,
    doors,
    windows,
    dimensions: { totalWidth: width, totalDepth: depth },
    template: "single_family",
    stories,
    footprintSqft: Math.round(footprintSqft),
    totalFloorAreaSqft: Math.round(totalFloorArea),
    maxAllowedFloorArea: Math.round(farLimit !== Infinity ? farLimit : footprintSqft * stories),
    lotCoverageUsedPct: Math.round(lotCoverageUsed * 10) / 10,
    lotCoverageAllowedPct: coverageAllowed,
    unitCount: 1,
    minUnitSizeSqft: input.minUnitSizeSqft,
    complianceNotes,
  };
}

// ---------------------------------------------------------------------------
// Duplex layout
// ---------------------------------------------------------------------------

function generateDuplex(input: FloorPlanInput): FloorPlanLayout {
  const { width, depth, footprintSqft } = computeEffectiveFootprint(input);
  const stories = computeStories(input);
  const farLimit = input.far > 0 ? input.far * input.lotSizeSqft : Infinity;
  const totalFloorArea = Math.min(footprintSqft * stories, farLimit);

  const rooms: Room[] = [];
  const doors: Door[] = [];
  const windows: Window[] = [];

  const sharedWallThickness = 0.5; // visual only
  const unitWidth = (width - sharedWallThickness) / 2;
  const unitArea = (unitWidth * depth * stories);

  // Side-by-side duplex
  for (let unit = 0; unit < 2; unit++) {
    const offsetX = unit * (unitWidth + sharedWallThickness);
    const unitLabel = unit === 0 ? "A" : "B";

    // Living (front)
    const livingD = clamp(depth * 0.35, 12, 16);
    rooms.push({
      name: `Living ${unitLabel}`,
      x: offsetX, y: 0,
      width: unitWidth, depth: livingD,
      floor: 1, type: "living", isWetRoom: false,
    });
    doors.push({
      x: offsetX + (unit === 0 ? unitWidth * 0.3 : unitWidth * 0.7),
      y: 0, wall: "south", width: 3, isExterior: true,
    });
    windows.push({
      x: offsetX + (unit === 0 ? unitWidth * 0.7 : unitWidth * 0.3),
      y: 0, wall: "south", width: 3,
    });

    // Kitchen (mid)
    const kitchenD = clamp(depth * 0.25, 8, 12);
    rooms.push({
      name: `Kitchen ${unitLabel}`,
      x: offsetX, y: livingD,
      width: unitWidth, depth: kitchenD,
      floor: 1, type: "kitchen", isWetRoom: true,
    });

    // Bedroom 1 (back-left of unit)
    const bedW = unitWidth * 0.55;
    const bedD = clamp(depth - livingD - kitchenD, 10, 16);
    rooms.push({
      name: `Bed 1 ${unitLabel}`,
      x: offsetX, y: livingD + kitchenD,
      width: bedW, depth: bedD,
      floor: 1, type: "bedroom", isWetRoom: false,
    });
    windows.push({
      x: offsetX + bedW / 2,
      y: livingD + kitchenD + bedD, wall: "north", width: 3,
    });

    // Bath (back-right of unit)
    const bathW = unitWidth - bedW;
    const bathD = clamp(bedD * 0.5, 5, 8);
    rooms.push({
      name: `Bath ${unitLabel}`,
      x: offsetX + bedW, y: livingD + kitchenD,
      width: bathW, depth: bathD,
      floor: 1, type: "bathroom", isWetRoom: true,
    });

    // Bedroom 2 (if 2-story, put upstairs)
    if (stories >= 2) {
      rooms.push({
        name: `Bed 2 ${unitLabel}`,
        x: offsetX, y: 0,
        width: unitWidth, depth: depth * 0.5,
        floor: 2, type: "bedroom", isWetRoom: false,
      });
      rooms.push({
        name: `Bath 2 ${unitLabel}`,
        x: offsetX, y: depth * 0.5,
        width: unitWidth * 0.4, depth: depth * 0.2,
        floor: 2, type: "bathroom", isWetRoom: true,
      });
    }

    // Side windows
    const sideWall = unit === 0 ? "west" : "east";
    const sideX = unit === 0 ? offsetX : offsetX + unitWidth;
    windows.push({ x: sideX, y: depth * 0.3, wall: sideWall, width: 3 });
    windows.push({ x: sideX, y: depth * 0.7, wall: sideWall, width: 3 });
  }

  const complianceNotes: string[] = [];
  const lotCoverageUsed = input.lotSizeSqft > 0 ? (footprintSqft / input.lotSizeSqft) * 100 : 0;
  const coverageAllowed = input.maxLotCoveragePct || 100;

  if (unitArea < input.minUnitSizeSqft) {
    complianceNotes.push(`WARNING: Unit area ${Math.round(unitArea)} sqft < min ${input.minUnitSizeSqft} sqft`);
  }
  complianceNotes.push(`Each unit: ~${Math.round(unitArea)} sqft`);
  if (coverageAllowed < 100) {
    complianceNotes.push(`Lot coverage ${Math.round(lotCoverageUsed)}% of ${coverageAllowed}% max`);
  }

  return {
    rooms, doors, windows,
    dimensions: { totalWidth: width, totalDepth: depth },
    template: "duplex",
    stories,
    footprintSqft: Math.round(footprintSqft),
    totalFloorAreaSqft: Math.round(totalFloorArea),
    maxAllowedFloorArea: Math.round(farLimit !== Infinity ? farLimit : footprintSqft * stories),
    lotCoverageUsedPct: Math.round(lotCoverageUsed * 10) / 10,
    lotCoverageAllowedPct: coverageAllowed,
    unitCount: 2,
    minUnitSizeSqft: input.minUnitSizeSqft,
    complianceNotes,
  };
}

// ---------------------------------------------------------------------------
// Multifamily layout (3-8 units)
// ---------------------------------------------------------------------------

function generateMultifamily(input: FloorPlanInput): FloorPlanLayout {
  const { width, depth, footprintSqft } = computeEffectiveFootprint(input);
  const stories = computeStories(input);
  const farLimit = input.far > 0 ? input.far * input.lotSizeSqft : Infinity;
  const totalFloorArea = Math.min(footprintSqft * stories, farLimit);
  const unitCount = input.maxUnits;

  const rooms: Room[] = [];
  const doors: Door[] = [];
  const windows: Window[] = [];

  const corridorWidth = 5;
  const stairwellWidth = 8;
  const stairwellDepth = 10;

  const unitsPerFloor = Math.ceil(unitCount / stories);
  const usableWidth = width - corridorWidth;
  const unitWidth = usableWidth / 2; // units on each side of corridor
  const unitDepth = Math.max((depth - stairwellDepth) / Math.ceil(unitsPerFloor / 2), 12);

  for (let floor = 1; floor <= stories; floor++) {
    const floorUnitsStart = (floor - 1) * unitsPerFloor;
    const floorUnitsEnd = Math.min(floorUnitsStart + unitsPerFloor, unitCount);

    // Central corridor
    rooms.push({
      name: `Corridor F${floor}`,
      x: unitWidth, y: 0,
      width: corridorWidth, depth: depth,
      floor, type: "corridor", isWetRoom: false,
    });

    // Stairwell at back
    rooms.push({
      name: `Stairs F${floor}`,
      x: unitWidth + (corridorWidth - stairwellWidth) / 2, y: depth - stairwellDepth,
      width: stairwellWidth, depth: stairwellDepth,
      floor, type: "stairwell", isWetRoom: false,
    });

    let unitIdx = 0;
    for (let u = floorUnitsStart; u < floorUnitsEnd; u++) {
      const side = unitIdx % 2 === 0 ? "left" : "right";
      const row = Math.floor(unitIdx / 2);
      const unitX = side === "left" ? 0 : unitWidth + corridorWidth;
      const unitY = row * unitDepth;
      const unitNum = u + 1;

      if (unitY + unitDepth > depth - stairwellDepth + 2) break;

      // Main living/kitchen area
      const livingW = unitWidth;
      const livingD = unitDepth * 0.5;
      rooms.push({
        name: `Unit ${unitNum} Living`,
        x: unitX, y: unitY,
        width: livingW, depth: livingD,
        floor, type: "living", isWetRoom: false,
      });

      // Bedroom
      const bedW = unitWidth * 0.6;
      const bedD = unitDepth * 0.35;
      rooms.push({
        name: `Unit ${unitNum} Bed`,
        x: unitX, y: unitY + livingD,
        width: bedW, depth: bedD,
        floor, type: "bedroom", isWetRoom: false,
      });

      // Bath
      const bathW = unitWidth - bedW;
      const bathD = bedD;
      rooms.push({
        name: `Unit ${unitNum} Bath`,
        x: unitX + bedW, y: unitY + livingD,
        width: bathW, depth: bathD,
        floor, type: "bathroom", isWetRoom: true,
      });

      // Door to corridor
      const doorX = side === "left" ? unitX + unitWidth : unitX;
      doors.push({
        x: doorX, y: unitY + unitDepth * 0.25,
        wall: side === "left" ? "east" : "west",
        width: 3, isExterior: false,
      });

      // Exterior windows
      const extWall = side === "left" ? "west" : "east";
      const winX = side === "left" ? unitX : unitX + unitWidth;
      windows.push({ x: winX, y: unitY + livingD * 0.5, wall: extWall, width: 4 });
      windows.push({ x: winX, y: unitY + livingD + bedD * 0.5, wall: extWall, width: 3 });

      unitIdx++;
    }

    // Entry door on ground floor
    if (floor === 1) {
      doors.push({
        x: unitWidth + corridorWidth / 2, y: 0,
        wall: "south", width: 4, isExterior: true,
      });
    }
  }

  const complianceNotes: string[] = [];
  const lotCoverageUsed = input.lotSizeSqft > 0 ? (footprintSqft / input.lotSizeSqft) * 100 : 0;
  const unitArea = totalFloorArea / unitCount;

  if (unitArea < input.minUnitSizeSqft) {
    complianceNotes.push(`WARNING: Avg unit area ${Math.round(unitArea)} sqft < min ${input.minUnitSizeSqft} sqft`);
  }
  complianceNotes.push(`${unitCount} units across ${stories} floor(s), ~${Math.round(unitArea)} sqft/unit`);
  if (input.maxLotCoveragePct > 0 && input.maxLotCoveragePct < 100) {
    complianceNotes.push(`Lot coverage ${Math.round(lotCoverageUsed)}% of ${input.maxLotCoveragePct}% max`);
  }

  return {
    rooms, doors, windows,
    dimensions: { totalWidth: width, totalDepth: depth },
    template: "multifamily",
    stories,
    footprintSqft: Math.round(footprintSqft),
    totalFloorAreaSqft: Math.round(totalFloorArea),
    maxAllowedFloorArea: Math.round(farLimit !== Infinity ? farLimit : footprintSqft * stories),
    lotCoverageUsedPct: Math.round(lotCoverageUsed * 10) / 10,
    lotCoverageAllowedPct: input.maxLotCoveragePct || 100,
    unitCount,
    minUnitSizeSqft: input.minUnitSizeSqft,
    complianceNotes,
  };
}

// ---------------------------------------------------------------------------
// Commercial layout
// ---------------------------------------------------------------------------

function generateCommercial(input: FloorPlanInput): FloorPlanLayout {
  const { width, depth, footprintSqft } = computeEffectiveFootprint(input);
  const stories = computeStories(input);
  const farLimit = input.far > 0 ? input.far * input.lotSizeSqft : Infinity;
  const totalFloorArea = Math.min(footprintSqft * stories, farLimit);

  const rooms: Room[] = [];
  const doors: Door[] = [];
  const windows: Window[] = [];

  const columnSpacing = clamp(width / Math.ceil(width / 28), 20, 30);

  for (let floor = 1; floor <= stories; floor++) {
    // Open floor plate
    rooms.push({
      name: floor === 1 ? "Retail / Office" : `Floor ${floor}`,
      x: 0, y: 0,
      width: width, depth: depth,
      floor, type: "open_floor", isWetRoom: false,
    });

    // Restroom core (back center)
    const coreW = clamp(width * 0.15, 10, 16);
    const coreD = clamp(depth * 0.15, 8, 12);
    rooms.push({
      name: `Restrooms F${floor}`,
      x: (width - coreW) / 2, y: depth - coreD,
      width: coreW, depth: coreD,
      floor, type: "bathroom", isWetRoom: true,
    });

    // Mechanical (back corner)
    const mechW = clamp(width * 0.1, 8, 12);
    const mechD = clamp(depth * 0.1, 6, 10);
    rooms.push({
      name: `Mech F${floor}`,
      x: width - mechW, y: depth - mechD,
      width: mechW, depth: mechD,
      floor, type: "mechanical", isWetRoom: false,
    });

    // Lobby / entry on ground floor
    if (floor === 1) {
      const lobbyW = clamp(width * 0.3, 12, 20);
      const lobbyD = clamp(depth * 0.15, 8, 12);
      rooms.push({
        name: "Lobby",
        x: (width - lobbyW) / 2, y: 0,
        width: lobbyW, depth: lobbyD,
        floor: 1, type: "lobby", isWetRoom: false,
      });
      doors.push({
        x: width / 2, y: 0,
        wall: "south", width: 6, isExterior: true,
      });
    }

    if (stories > 1) {
      rooms.push({
        name: `Stairs F${floor}`,
        x: 0, y: depth - 10,
        width: 8, depth: 10,
        floor, type: "stairwell", isWetRoom: false,
      });
    }

    // Storefront windows (front)
    for (let wx = 4; wx < width - 4; wx += 8) {
      windows.push({ x: wx, y: 0, wall: "south", width: 6 });
    }
    // Side windows
    for (let wy = 6; wy < depth - 6; wy += 10) {
      windows.push({ x: 0, y: wy, wall: "west", width: 4 });
      windows.push({ x: width, y: wy, wall: "east", width: 4 });
    }
  }

  const complianceNotes: string[] = [];
  const lotCoverageUsed = input.lotSizeSqft > 0 ? (footprintSqft / input.lotSizeSqft) * 100 : 0;

  complianceNotes.push(`GLA: ~${Math.round(totalFloorArea).toLocaleString()} sqft across ${stories} floor(s)`);
  complianceNotes.push(`Column grid: ~${Math.round(columnSpacing)}ft spacing`);
  if (input.maxLotCoveragePct > 0 && input.maxLotCoveragePct < 100) {
    complianceNotes.push(`Lot coverage ${Math.round(lotCoverageUsed)}% of ${input.maxLotCoveragePct}% max`);
  }

  return {
    rooms, doors, windows,
    dimensions: { totalWidth: width, totalDepth: depth },
    template: "commercial",
    stories,
    footprintSqft: Math.round(footprintSqft),
    totalFloorAreaSqft: Math.round(totalFloorArea),
    maxAllowedFloorArea: Math.round(farLimit !== Infinity ? farLimit : footprintSqft * stories),
    lotCoverageUsedPct: Math.round(lotCoverageUsed * 10) / 10,
    lotCoverageAllowedPct: input.maxLotCoveragePct || 100,
    unitCount: 0,
    minUnitSizeSqft: 0,
    complianceNotes,
  };
}

// ---------------------------------------------------------------------------
// Public API
// ---------------------------------------------------------------------------

export function generateFloorPlan(input: FloorPlanInput): FloorPlanLayout {
  if (input.buildableWidthFt <= 0 || input.buildableDepthFt <= 0) {
    return {
      rooms: [], doors: [], windows: [],
      dimensions: { totalWidth: 0, totalDepth: 0 },
      template: "invalid", stories: 0,
      footprintSqft: 0, totalFloorAreaSqft: 0, maxAllowedFloorArea: 0,
      lotCoverageUsedPct: 0, lotCoverageAllowedPct: 0,
      unitCount: 0, minUnitSizeSqft: 0,
      complianceNotes: ["Invalid buildable dimensions"],
    };
  }

  const pt = (input.propertyType || "").toLowerCase();
  if (pt === "commercial" || pt === "commercial_mf") {
    if (input.maxUnits <= 0 || pt === "commercial") {
      return generateCommercial(input);
    }
  }

  if (input.maxUnits >= 3) return generateMultifamily(input);
  if (input.maxUnits === 2) return generateDuplex(input);
  return generateSingleFamily(input);
}
