"use client";

import { FloorPlanLayout, Room, Door, Window } from "@/lib/floorplan-generator";

// ---------------------------------------------------------------------------
// Architectural style constants
// ---------------------------------------------------------------------------

const ROOM_FILLS: Record<string, string> = {
  living: "#FAFAF8",
  kitchen: "#F5F2ED",
  dining: "#FAF8F5",
  bedroom: "#FAFAF8",
  bathroom: "#EDF2F8",
  garage: "#F0EDEA",
  laundry: "#EDF2F8",
  entry: "#FAF8F5",
  hallway: "#F5F2ED",
  closet: "#F0EDEA",
  corridor: "#F0EDEA",
  stairwell: "#E8E5E0",
  mechanical: "#E8E5E0",
  lobby: "#FAF8F5",
  open_floor: "#FAFAF8",
};

const WALL_EXT = 4;       // Exterior wall stroke
const WALL_INT = 1.5;     // Interior wall stroke
const MARGIN = 55;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function ftLabel(ft: number): string {
  const whole = Math.floor(ft);
  const inches = Math.round((ft - whole) * 12);
  return inches > 0 ? `${whole}-${inches}` : `${whole}-0`;
}

// ---------------------------------------------------------------------------
// Detailed furniture SVG icons
// ---------------------------------------------------------------------------

function LivingFurniture({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  if (w < 35 || h < 35) return null;
  const cx = x + w / 2;
  const cy = y + h / 2;

  // L-shaped sofa
  const sofaW = Math.min(w * 0.55, 42);
  const sofaH = Math.min(h * 0.14, 10);
  const armW = sofaH * 0.8;

  return (
    <g stroke="#888" strokeWidth={0.7} fill="none">
      {/* Sofa back */}
      <rect x={cx - sofaW / 2} y={cy + h * 0.08} width={sofaW} height={sofaH} rx={1.5} />
      {/* Sofa seat cushions */}
      <line x1={cx - sofaW / 4} y1={cy + h * 0.08} x2={cx - sofaW / 4} y2={cy + h * 0.08 + sofaH} />
      <line x1={cx + sofaW / 4} y1={cy + h * 0.08} x2={cx + sofaW / 4} y2={cy + h * 0.08 + sofaH} />
      {/* Sofa arm (L-shape) */}
      <rect x={cx - sofaW / 2} y={cy + h * 0.08 - armW} width={sofaH} height={armW + sofaH} rx={1} />

      {/* Coffee table */}
      <rect x={cx - sofaW * 0.15} y={cy - h * 0.02} width={sofaW * 0.3} height={sofaH * 0.5} rx={1} strokeWidth={0.6} />

      {/* Accent chair */}
      <rect x={cx + sofaW / 2 + 3} y={cy + h * 0.06} width={sofaH * 0.9} height={sofaH * 1.1} rx={2} strokeWidth={0.6} />
    </g>
  );
}

function KitchenFurniture({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  if (w < 30 || h < 30) return null;

  const counterW = Math.min(w * 0.85, 50);
  const counterH = Math.min(h * 0.1, 5);

  return (
    <g stroke="#888" strokeWidth={0.7} fill="none">
      {/* L-shaped counter along top and left */}
      <rect x={x + 3} y={y + 3} width={counterW} height={counterH} />
      <rect x={x + 3} y={y + 3} width={counterH} height={Math.min(h * 0.4, 22)} />

      {/* Double sink */}
      <ellipse cx={x + counterW * 0.4} cy={y + 3 + counterH / 2} rx={2.5} ry={1.8} strokeWidth={0.5} />
      <ellipse cx={x + counterW * 0.5} cy={y + 3 + counterH / 2} rx={2.5} ry={1.8} strokeWidth={0.5} />

      {/* Stove (4 burners) */}
      <rect x={x + counterW * 0.65} y={y + 2} width={counterH * 1.5} height={counterH + 2} strokeWidth={0.5} />
      {[0, 1, 2, 3].map((i) => (
        <circle
          key={i}
          cx={x + counterW * 0.65 + counterH * 0.4 + (i % 2) * counterH * 0.7}
          cy={y + 3 + (Math.floor(i / 2)) * counterH * 0.6}
          r={1.2} strokeWidth={0.4}
        />
      ))}

      {/* Refrigerator */}
      <rect x={x + 3 + counterH + 1} y={y + 3 + counterH + 2} width={counterH * 1.2} height={counterH * 1.8} strokeWidth={0.6} />
      <line
        x1={x + 3 + counterH + 1 + counterH * 0.6}
        y1={y + 3 + counterH + 2}
        x2={x + 3 + counterH + 1 + counterH * 0.6}
        y2={y + 3 + counterH + 2 + counterH * 1.8}
        strokeWidth={0.4}
      />

      {/* Island (if kitchen is large enough) */}
      {w > 50 && h > 50 && (
        <rect x={x + w * 0.35} y={y + h * 0.45} width={w * 0.3} height={counterH * 1.5} rx={1} strokeWidth={0.5} />
      )}
    </g>
  );
}

function DiningFurniture({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  if (w < 28 || h < 25) return null;
  const cx = x + w / 2;
  const cy = y + h / 2;
  const tw = Math.min(w * 0.4, 20);
  const th = Math.min(h * 0.3, 12);
  const chairW = 3;

  return (
    <g stroke="#888" strokeWidth={0.6} fill="none">
      {/* Table */}
      <rect x={cx - tw / 2} y={cy - th / 2} width={tw} height={th} rx={2} strokeWidth={0.7} />

      {/* Chairs around table */}
      {/* Top row */}
      {[-tw / 3, 0, tw / 3].map((dx, i) => (
        <rect key={`t${i}`} x={cx + dx - chairW / 2} y={cy - th / 2 - chairW - 1} width={chairW} height={chairW} rx={0.5} />
      ))}
      {/* Bottom row */}
      {[-tw / 3, 0, tw / 3].map((dx, i) => (
        <rect key={`b${i}`} x={cx + dx - chairW / 2} y={cy + th / 2 + 1} width={chairW} height={chairW} rx={0.5} />
      ))}
      {/* Sides */}
      <rect x={cx - tw / 2 - chairW - 1} y={cy - chairW / 2} width={chairW} height={chairW} rx={0.5} />
      <rect x={cx + tw / 2 + 1} y={cy - chairW / 2} width={chairW} height={chairW} rx={0.5} />
    </g>
  );
}

function BedroomFurniture({ x, y, w, h, isMaster }: { x: number; y: number; w: number; h: number; isMaster: boolean }) {
  if (w < 28 || h < 28) return null;
  const cx = x + w / 2;

  const bedW = isMaster ? Math.min(w * 0.45, 24) : Math.min(w * 0.4, 18);
  const bedH = isMaster ? Math.min(h * 0.4, 18) : Math.min(h * 0.35, 14);

  return (
    <g stroke="#888" strokeWidth={0.6} fill="none">
      {/* Bed frame */}
      <rect x={cx - bedW / 2} y={y + h * 0.3} width={bedW} height={bedH} rx={1} strokeWidth={0.7} />
      {/* Headboard */}
      <rect x={cx - bedW / 2 - 0.5} y={y + h * 0.3 - 2} width={bedW + 1} height={2.5} rx={0.5} fill="#DDD8D0" stroke="#999" strokeWidth={0.5} />
      {/* Pillows */}
      <rect x={cx - bedW / 2 + 2} y={y + h * 0.3 + 1} width={bedW / 2 - 3} height={3} rx={1.5} />
      <rect x={cx + 1} y={y + h * 0.3 + 1} width={bedW / 2 - 3} height={3} rx={1.5} />

      {/* Nightstands */}
      <rect x={cx - bedW / 2 - 5} y={y + h * 0.3} width={4} height={4} rx={0.5} strokeWidth={0.5} />
      <rect x={cx + bedW / 2 + 1} y={y + h * 0.3} width={4} height={4} rx={0.5} strokeWidth={0.5} />
    </g>
  );
}

function BathroomFurniture({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  if (w < 18 || h < 18) return null;

  return (
    <g stroke="#888" strokeWidth={0.6} fill="none">
      {/* Bathtub */}
      <rect x={x + 3} y={y + 3} width={Math.min(w * 0.4, 14)} height={Math.min(h * 0.25, 8)} rx={3} strokeWidth={0.7} />
      {/* Drain */}
      <circle cx={x + 3 + Math.min(w * 0.2, 7)} cy={y + 3 + Math.min(h * 0.125, 4)} r={0.8} strokeWidth={0.4} />

      {/* Toilet */}
      <ellipse cx={x + w * 0.7} cy={y + h * 0.35} rx={2.5} ry={3.5} strokeWidth={0.6} />
      {/* Tank */}
      <rect x={x + w * 0.7 - 2.5} y={y + h * 0.35 + 3} width={5} height={2.5} rx={1} strokeWidth={0.5} />

      {/* Vanity/sink */}
      <rect x={x + w * 0.3} y={y + h - 7} width={Math.min(w * 0.4, 14)} height={4} rx={0.5} strokeWidth={0.5} />
      <ellipse cx={x + w * 0.3 + Math.min(w * 0.2, 7)} cy={y + h - 5} rx={2} ry={1.5} strokeWidth={0.4} />
    </g>
  );
}

function GarageFurniture({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  if (w < 35 || h < 30) return null;
  const cx = x + w / 2;
  const cy = y + h / 2;

  const carW = Math.min(w * 0.25, 12);
  const carH = Math.min(h * 0.55, 28);
  const gap = carW * 0.6;

  return (
    <g stroke="#999" strokeWidth={0.6} fill="none" strokeDasharray="2.5,1.5">
      {/* Car 1 */}
      <rect x={cx - gap - carW} y={cy - carH / 2} width={carW} height={carH} rx={3} />
      {/* Windshield */}
      <line x1={cx - gap - carW + 2} y1={cy - carH * 0.25} x2={cx - gap - 2} y2={cy - carH * 0.25} strokeWidth={0.4} />
      {/* Car 2 */}
      <rect x={cx + gap} y={cy - carH / 2} width={carW} height={carH} rx={3} />
      <line x1={cx + gap + 2} y1={cy - carH * 0.25} x2={cx + gap + carW - 2} y2={cy - carH * 0.25} strokeWidth={0.4} />
    </g>
  );
}

function StairsFurniture({ x, y, w, h }: { x: number; y: number; w: number; h: number }) {
  if (w < 15 || h < 15) return null;
  const treadCount = Math.min(Math.floor(h / 2.5), 10);
  const treadH = h / (treadCount + 1);

  return (
    <g stroke="#999" strokeWidth={0.4} fill="none">
      {Array.from({ length: treadCount }, (_, i) => (
        <line key={i} x1={x + 2} y1={y + (i + 1) * treadH} x2={x + w - 2} y2={y + (i + 1) * treadH} />
      ))}
      {/* Arrow showing up direction */}
      <line x1={x + w / 2} y1={y + h - 3} x2={x + w / 2} y2={y + 3} strokeWidth={0.6} />
      <line x1={x + w / 2 - 2} y1={y + 6} x2={x + w / 2} y2={y + 3} strokeWidth={0.6} />
      <line x1={x + w / 2 + 2} y1={y + 6} x2={x + w / 2} y2={y + 3} strokeWidth={0.6} />
      <text x={x + w / 2} y={y + h - 1} textAnchor="middle" fill="#999" fontSize="5" fontFamily="system-ui">UP</text>
    </g>
  );
}

// ---------------------------------------------------------------------------
// Landscaping
// ---------------------------------------------------------------------------

function LandscapeTree({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <g>
      <circle cx={cx} cy={cy} r={r} fill="#C8D8C0" stroke="#8AAA78" strokeWidth={0.5} opacity={0.7} />
      {/* Inner foliage circles */}
      <circle cx={cx - r * 0.25} cy={cy - r * 0.2} r={r * 0.5} fill="none" stroke="#8AAA78" strokeWidth={0.3} />
      <circle cx={cx + r * 0.2} cy={cy + r * 0.15} r={r * 0.45} fill="none" stroke="#8AAA78" strokeWidth={0.3} />
      {/* Trunk */}
      <circle cx={cx} cy={cy} r={r * 0.12} fill="#A08060" stroke="none" />
    </g>
  );
}

function LandscapeBush({ cx, cy, r }: { cx: number; cy: number; r: number }) {
  return (
    <circle cx={cx} cy={cy} r={r} fill="#D0E0C8" stroke="#90B078" strokeWidth={0.4} opacity={0.6} />
  );
}

// ---------------------------------------------------------------------------
// Room renderer with proper walls + hatching for wet rooms
// ---------------------------------------------------------------------------

function RoomBlock({ room, scale }: { room: Room; scale: number }) {
  const x = MARGIN + room.x * scale;
  const y = MARGIN + room.y * scale;
  const w = room.width * scale;
  const h = room.depth * scale;
  const fill = ROOM_FILLS[room.type] || "#FAFAF8";
  const isWet = room.isWetRoom;
  const isExt = room.type === "garage" || room.type === "entry";
  const wallW = isExt ? WALL_EXT : WALL_INT;

  const dimStr = `${ftLabel(room.width)} x ${ftLabel(room.depth)}`;
  const nameParts = room.name.toUpperCase().split(" ");

  return (
    <g>
      {/* Room fill */}
      <rect x={x} y={y} width={w} height={h} fill={fill} />

      {/* Wet room diagonal hatching */}
      {isWet && (
        <g>
          <defs>
            <pattern id={`hatch-${room.name.replace(/\s/g, "")}-${room.floor}`} patternUnits="userSpaceOnUse" width="6" height="6" patternTransform="rotate(45)">
              <line x1="0" y1="0" x2="0" y2="6" stroke="#C8D8E8" strokeWidth="0.4" />
            </pattern>
          </defs>
          <rect x={x} y={y} width={w} height={h} fill={`url(#hatch-${room.name.replace(/\s/g, "")}-${room.floor})`} />
        </g>
      )}

      {/* Room walls */}
      <rect x={x} y={y} width={w} height={h} fill="none" stroke="#2A2520" strokeWidth={wallW} />

      {/* Room label */}
      {w > 28 && h > 22 && (
        <g>
          {nameParts.length <= 2 ? (
            <text
              x={x + w / 2} y={y + h / 2 - 3}
              textAnchor="middle" dominantBaseline="middle"
              fill="#2A2520" fontSize="8" fontWeight="600" fontFamily="system-ui"
              letterSpacing="0.5"
            >
              {room.name.toUpperCase()}
            </text>
          ) : (
            <>
              <text
                x={x + w / 2} y={y + h / 2 - 7}
                textAnchor="middle" fill="#2A2520" fontSize="7.5" fontWeight="600" fontFamily="system-ui" letterSpacing="0.5"
              >
                {nameParts.slice(0, 2).join(" ")}
              </text>
              <text
                x={x + w / 2} y={y + h / 2}
                textAnchor="middle" fill="#2A2520" fontSize="7.5" fontWeight="600" fontFamily="system-ui" letterSpacing="0.5"
              >
                {nameParts.slice(2).join(" ")}
              </text>
            </>
          )}
          <text
            x={x + w / 2} y={y + h / 2 + 8}
            textAnchor="middle" dominantBaseline="middle"
            fill="#78716c" fontSize="7" fontFamily="system-ui"
          >
            {dimStr}
          </text>
        </g>
      )}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Door swing arc (architectural style)
// ---------------------------------------------------------------------------

function DoorSwing({ door, scale }: { door: Door; scale: number }) {
  const cx = MARGIN + door.x * scale;
  const cy = MARGIN + door.y * scale;
  const r = (door.width * scale) * 0.45;
  const stroke = door.isExterior ? "#2A2520" : "#666";
  const sw = door.isExterior ? 1.2 : 0.8;

  // Door line + quarter arc
  let doorLine = "";
  let arcPath = "";

  if (door.wall === "south") {
    doorLine = `M ${cx - r} ${cy} L ${cx + r} ${cy}`;
    arcPath = `M ${cx - r} ${cy} A ${r} ${r} 0 0 0 ${cx - r} ${cy + r}`;
  } else if (door.wall === "north") {
    doorLine = `M ${cx - r} ${cy} L ${cx + r} ${cy}`;
    arcPath = `M ${cx + r} ${cy} A ${r} ${r} 0 0 0 ${cx + r} ${cy - r}`;
  } else if (door.wall === "east") {
    doorLine = `M ${cx} ${cy - r} L ${cx} ${cy + r}`;
    arcPath = `M ${cx} ${cy - r} A ${r} ${r} 0 0 1 ${cx + r} ${cy - r}`;
  } else {
    doorLine = `M ${cx} ${cy - r} L ${cx} ${cy + r}`;
    arcPath = `M ${cx} ${cy + r} A ${r} ${r} 0 0 1 ${cx - r} ${cy + r}`;
  }

  return (
    <g>
      {/* Door leaf */}
      <path d={doorLine} stroke={stroke} strokeWidth={sw + 0.5} fill="none" />
      {/* Swing arc — dashed */}
      <path d={arcPath} stroke={stroke} strokeWidth={sw} fill="none" strokeDasharray="2,1.5" />
      {/* Break in wall (opening) */}
      {door.isExterior && (
        <rect
          x={door.wall === "east" || door.wall === "west" ? cx - 2 : cx - r}
          y={door.wall === "south" || door.wall === "north" ? cy - 2 : cy - r}
          width={door.wall === "east" || door.wall === "west" ? 4 : r * 2}
          height={door.wall === "south" || door.wall === "north" ? 4 : r * 2}
          fill="#FAFAF8" stroke="none"
        />
      )}
    </g>
  );
}

// ---------------------------------------------------------------------------
// Window mark (architectural: three parallel lines on wall)
// ---------------------------------------------------------------------------

function WindowLine({ win, scale }: { win: Window; scale: number }) {
  const cx = MARGIN + win.x * scale;
  const cy = MARGIN + win.y * scale;
  const halfW = (win.width * scale) / 2;

  const isHoriz = win.wall === "south" || win.wall === "north";
  const offset = 1.5;

  if (isHoriz) {
    return (
      <g>
        <line x1={cx - halfW} y1={cy - offset} x2={cx + halfW} y2={cy - offset} stroke="#2A2520" strokeWidth={1.8} />
        <line x1={cx - halfW} y1={cy} x2={cx + halfW} y2={cy} stroke="#AAC8E8" strokeWidth={1} />
        <line x1={cx - halfW} y1={cy + offset} x2={cx + halfW} y2={cy + offset} stroke="#2A2520" strokeWidth={1.8} />
      </g>
    );
  }
  return (
    <g>
      <line x1={cx - offset} y1={cy - halfW} x2={cx - offset} y2={cy + halfW} stroke="#2A2520" strokeWidth={1.8} />
      <line x1={cx} y1={cy - halfW} x2={cx} y2={cy + halfW} stroke="#AAC8E8" strokeWidth={1} />
      <line x1={cx + offset} y1={cy - halfW} x2={cx + offset} y2={cy + halfW} stroke="#2A2520" strokeWidth={1.8} />
    </g>
  );
}

// ---------------------------------------------------------------------------
// Furniture dispatcher
// ---------------------------------------------------------------------------

function RoomFurniture({ room, scale }: { room: Room; scale: number }) {
  const x = MARGIN + room.x * scale;
  const y = MARGIN + room.y * scale;
  const w = room.width * scale;
  const h = room.depth * scale;

  switch (room.type) {
    case "living": return <LivingFurniture x={x} y={y} w={w} h={h} />;
    case "kitchen": return <KitchenFurniture x={x} y={y} w={w} h={h} />;
    case "dining": return <DiningFurniture x={x} y={y} w={w} h={h} />;
    case "bedroom": return <BedroomFurniture x={x} y={y} w={w} h={h} isMaster={room.name.toLowerCase().includes("master")} />;
    case "bathroom": return <BathroomFurniture x={x} y={y} w={w} h={h} />;
    case "garage": return <GarageFurniture x={x} y={y} w={w} h={h} />;
    case "stairwell": return <StairsFurniture x={x} y={y} w={w} h={h} />;
    default: return null;
  }
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface FloorPlanSVGProps {
  layout: FloorPlanLayout;
  zoningDistrict?: string;
}

export default function FloorPlanSVG({ layout, zoningDistrict }: FloorPlanSVGProps) {
  if (!layout.rooms.length) return null;

  const { totalWidth, totalDepth } = layout.dimensions;
  const floors = layout.stories;

  const targetWidth = 560;
  const scale = targetWidth / Math.max(totalWidth, 1);
  const svgContentW = totalWidth * scale;
  const svgContentH = totalDepth * scale;
  const svgW = svgContentW + MARGIN * 2;
  const svgH = svgContentH + MARGIN * 2 + 60;
  const totalSvgW = floors > 1 ? svgW * Math.min(floors, 2) + 20 : svgW;

  const renderFloor = (floorNum: number, offsetX: number) => {
    const floorRooms = layout.rooms.filter((r) => r.floor === floorNum);

    return (
      <g key={floorNum} transform={`translate(${offsetX}, 0)`}>
        {/* Floor label */}
        <text
          x={svgW / 2} y={18}
          textAnchor="middle" fill="#2A2520" fontSize="11" fontWeight="700"
          fontFamily="system-ui" letterSpacing="1.5"
        >
          {floors > 1 ? `FLOOR ${floorNum}` : "FLOOR PLAN"}
        </text>

        {/* Thick exterior boundary (double line architectural style) */}
        <rect x={MARGIN - 2} y={MARGIN - 2} width={svgContentW + 4} height={svgContentH + 4}
          fill="none" stroke="#2A2520" strokeWidth={1} />
        <rect x={MARGIN} y={MARGIN} width={svgContentW} height={svgContentH}
          fill="#FAFAF8" stroke="#2A2520" strokeWidth={WALL_EXT} />

        {/* Rooms */}
        {floorRooms.map((room, i) => (
          <RoomBlock key={`r-${floorNum}-${i}`} room={room} scale={scale} />
        ))}

        {/* Furniture */}
        {floorRooms.map((room, i) => (
          <RoomFurniture key={`f-${floorNum}-${i}`} room={room} scale={scale} />
        ))}

        {/* Doors */}
        {floorNum === 1 && layout.doors.map((door, i) => (
          <DoorSwing key={`d-${i}`} door={door} scale={scale} />
        ))}

        {/* Windows */}
        {floorNum === 1 && layout.windows.map((win, i) => (
          <WindowLine key={`w-${i}`} win={win} scale={scale} />
        ))}

        {/* Landscaping — trees around perimeter */}
        {floorNum === 1 && (
          <g>
            <LandscapeTree cx={MARGIN - 12} cy={MARGIN + svgContentH * 0.3} r={8} />
            <LandscapeTree cx={MARGIN + svgContentW + 12} cy={MARGIN + svgContentH * 0.2} r={9} />
            <LandscapeTree cx={MARGIN + svgContentW + 10} cy={MARGIN + svgContentH * 0.7} r={7} />
            <LandscapeTree cx={MARGIN + svgContentW * 0.7} cy={MARGIN + svgContentH + 14} r={8} />
            <LandscapeTree cx={MARGIN - 10} cy={MARGIN + svgContentH * 0.75} r={6} />
            {/* Foundation bushes */}
            <LandscapeBush cx={MARGIN + svgContentW * 0.15} cy={MARGIN + svgContentH + 5} r={4} />
            <LandscapeBush cx={MARGIN + svgContentW * 0.35} cy={MARGIN + svgContentH + 4} r={3.5} />
            <LandscapeBush cx={MARGIN + svgContentW * 0.85} cy={MARGIN + svgContentH + 5} r={4} />
            <LandscapeBush cx={MARGIN - 5} cy={MARGIN + svgContentH * 0.5} r={3} />
          </g>
        )}

        {/* Dimension annotations — width (bottom) */}
        <g>
          {/* Witness lines */}
          <line x1={MARGIN} y1={MARGIN + svgContentH + 6} x2={MARGIN} y2={MARGIN + svgContentH + 18}
            stroke="#555" strokeWidth={0.4} />
          <line x1={MARGIN + svgContentW} y1={MARGIN + svgContentH + 6} x2={MARGIN + svgContentW} y2={MARGIN + svgContentH + 18}
            stroke="#555" strokeWidth={0.4} />
          {/* Dimension line */}
          <line x1={MARGIN + 2} y1={MARGIN + svgContentH + 14} x2={MARGIN + svgContentW - 2} y2={MARGIN + svgContentH + 14}
            stroke="#555" strokeWidth={0.5} markerStart="url(#dimArrowL)" markerEnd="url(#dimArrowR)" />
          <text x={MARGIN + svgContentW / 2} y={MARGIN + svgContentH + 27}
            textAnchor="middle" fill="#555" fontSize="8" fontFamily="system-ui">
            {ftLabel(totalWidth)}
          </text>
        </g>

        {/* Dimension — depth (left) */}
        <g>
          <line x1={MARGIN - 6} y1={MARGIN} x2={MARGIN - 18} y2={MARGIN}
            stroke="#555" strokeWidth={0.4} />
          <line x1={MARGIN - 6} y1={MARGIN + svgContentH} x2={MARGIN - 18} y2={MARGIN + svgContentH}
            stroke="#555" strokeWidth={0.4} />
          <line x1={MARGIN - 14} y1={MARGIN + 2} x2={MARGIN - 14} y2={MARGIN + svgContentH - 2}
            stroke="#555" strokeWidth={0.5} />
          <text
            x={MARGIN - 20} y={MARGIN + svgContentH / 2}
            textAnchor="middle" fill="#555" fontSize="8" fontFamily="system-ui"
            transform={`rotate(-90, ${MARGIN - 20}, ${MARGIN + svgContentH / 2})`}
          >
            {ftLabel(totalDepth)}
          </text>
        </g>
      </g>
    );
  };

  return (
    <div className="space-y-2">
      <div className="-mx-1 overflow-x-auto sm:mx-0">
        <svg
          viewBox={`0 0 ${totalSvgW} ${svgH}`}
          className="w-full"
          style={{ maxHeight: "550px" }}
          xmlns="http://www.w3.org/2000/svg"
        >
          <defs>
            <marker id="dimArrowL" markerWidth="5" markerHeight="5" refX="5" refY="2.5" orient="auto">
              <path d="M5,0 L0,2.5 L5,5" fill="none" stroke="#555" strokeWidth="0.6" />
            </marker>
            <marker id="dimArrowR" markerWidth="5" markerHeight="5" refX="0" refY="2.5" orient="auto">
              <path d="M0,0 L5,2.5 L0,5" fill="none" stroke="#555" strokeWidth="0.6" />
            </marker>
          </defs>

          {/* Background */}
          <rect width={totalSvgW} height={svgH} fill="white" rx={6} />

          {/* Render floors */}
          {Array.from({ length: Math.min(floors, 2) }, (_, i) => i + 1).map((f, idx) =>
            renderFloor(f, idx * (svgW + 10))
          )}
        </svg>
      </div>

      {/* Compliance bar */}
      <div className="rounded-lg border border-stone-200 bg-stone-50 px-3 py-2">
        {zoningDistrict && (
          <div className="mb-1.5 text-xs font-semibold uppercase tracking-wider text-stone-500">
            Proposed {layout.template.replace(/_/g, " ")} — {zoningDistrict} Compliant
          </div>
        )}
        <div className="flex flex-wrap gap-x-4 gap-y-1 text-xs">
          <span className="text-stone-600">
            Footprint: <span className="font-medium text-stone-800">{layout.footprintSqft.toLocaleString()} sqft</span>
          </span>
          {layout.lotCoverageAllowedPct < 100 && (
            <span className={layout.lotCoverageUsedPct > layout.lotCoverageAllowedPct * 0.9 ? "text-amber-600 font-medium" : "text-stone-600"}>
              Coverage: {layout.lotCoverageUsedPct}% / {layout.lotCoverageAllowedPct}% max
            </span>
          )}
          <span className="text-stone-600">
            Total: <span className="font-medium text-stone-800">{layout.totalFloorAreaSqft.toLocaleString()} sqft</span>
          </span>
          <span className="text-stone-600">
            {layout.stories} of {layout.stories} stories
          </span>
          {layout.unitCount > 0 && (
            <span className="text-stone-600">
              {layout.unitCount} unit{layout.unitCount !== 1 ? "s" : ""}
            </span>
          )}
        </div>
        {layout.complianceNotes.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-x-3 gap-y-0.5">
            {layout.complianceNotes.map((note, i) => (
              <span key={i} className={`text-xs ${note.startsWith("WARNING") ? "text-amber-600 font-medium" : "text-stone-500"}`}>
                {note}
              </span>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
