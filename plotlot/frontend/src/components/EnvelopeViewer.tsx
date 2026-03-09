"use client";

import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Text, Line, Grid } from "@react-three/drei";
import * as THREE from "three";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface EnvelopeViewerProps {
  lotWidthFt: number;
  lotDepthFt: number;
  setbackFrontFt: number;
  setbackSideFt: number;
  setbackRearFt: number;
  maxHeightFt: number;
  buildableAreaSqft?: number;
}

// ---------------------------------------------------------------------------
// Colours matching the stone/amber/emerald palette
// ---------------------------------------------------------------------------

const COLORS = {
  lotFill: "#d6cfc4", // stone-300 ish — tan ground
  setbackLine: "#d97706", // amber-600
  envelopeWall: "#059669", // emerald-600
  heightPlane: "#f59e0b", // amber-400
  labelText: "#44403c", // stone-700
  dimText: "#78716c", // stone-500
  gridLine: "#a8a29e", // stone-400
} as const;

// ---------------------------------------------------------------------------
// Sub-components rendered inside the Canvas
// ---------------------------------------------------------------------------

/** Flat lot polygon on the ground (y = 0) */
function LotPlane({ width, depth }: { width: number; depth: number }) {
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, 0.01, 0]} receiveShadow>
      <planeGeometry args={[width, depth]} />
      <meshStandardMaterial color={COLORS.lotFill} side={THREE.DoubleSide} />
    </mesh>
  );
}

/** Dashed setback outline drawn on the ground (y = 0.05) */
function SetbackOutline({
  lotWidth,
  lotDepth,
  front,
  side,
  rear,
}: {
  lotWidth: number;
  lotDepth: number;
  front: number;
  side: number;
  rear: number;
}) {
  const bw = lotWidth - 2 * side;
  const bd = lotDepth - front - rear;

  if (bw <= 0 || bd <= 0) return null;

  // Buildable footprint corners (front = +Z direction)
  const y = 0.05;
  const halfW = lotWidth / 2;
  const halfD = lotDepth / 2;

  const x0 = -halfW + side;
  const x1 = halfW - side;
  const z0 = -halfD + rear;
  const z1 = halfD - front;

  const points: [number, number, number][] = [
    [x0, y, z0],
    [x1, y, z0],
    [x1, y, z1],
    [x0, y, z1],
    [x0, y, z0], // close the loop
  ];

  return (
    <Line
      points={points}
      color={COLORS.setbackLine}
      lineWidth={2}
      dashed
      dashSize={2}
      gapSize={1}
    />
  );
}

/** Semi-transparent buildable envelope box */
function BuildableEnvelope({
  lotWidth,
  lotDepth,
  front,
  side,
  rear,
  height,
}: {
  lotWidth: number;
  lotDepth: number;
  front: number;
  side: number;
  rear: number;
  height: number;
}) {
  const bw = lotWidth - 2 * side;
  const bd = lotDepth - front - rear;

  if (bw <= 0 || bd <= 0 || height <= 0) return null;

  const halfW = lotWidth / 2;
  const halfD = lotDepth / 2;
  const cx = 0; // centred on X
  const cz = (-halfD + rear + (halfD - front)) / 2; // centred between rear setback and front setback
  const cy = height / 2;

  return (
    <mesh position={[cx, cy, cz]}>
      <boxGeometry args={[bw, height, bd]} />
      <meshStandardMaterial
        color={COLORS.envelopeWall}
        transparent
        opacity={0.18}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

/** Wireframe edges for the buildable envelope */
function EnvelopeEdges({
  lotWidth,
  lotDepth,
  front,
  side,
  rear,
  height,
}: {
  lotWidth: number;
  lotDepth: number;
  front: number;
  side: number;
  rear: number;
  height: number;
}) {
  const bw = lotWidth - 2 * side;
  const bd = lotDepth - front - rear;

  if (bw <= 0 || bd <= 0 || height <= 0) return null;

  const halfW = lotWidth / 2;
  const halfD = lotDepth / 2;
  const cx = 0;
  const cz = (-halfD + rear + (halfD - front)) / 2;
  const cy = height / 2;

  return (
    <lineSegments position={[cx, cy, cz]}>
      <edgesGeometry
        args={[new THREE.BoxGeometry(bw, height, bd)]}
      />
      <lineBasicMaterial color={COLORS.envelopeWall} linewidth={1} />
    </lineSegments>
  );
}

/** Translucent plane at max height */
function HeightPlane({
  lotWidth,
  lotDepth,
  height,
}: {
  lotWidth: number;
  lotDepth: number;
  height: number;
}) {
  if (height <= 0) return null;

  // Slightly larger than the lot so it's visible
  const pad = 2;
  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, height, 0]}>
      <planeGeometry args={[lotWidth + pad, lotDepth + pad]} />
      <meshStandardMaterial
        color={COLORS.heightPlane}
        transparent
        opacity={0.1}
        side={THREE.DoubleSide}
        depthWrite={false}
      />
    </mesh>
  );
}

/** Dimension annotation labels */
function DimensionLabels({
  lotWidth,
  lotDepth,
  front,
  side,
  rear,
  height,
}: {
  lotWidth: number;
  lotDepth: number;
  front: number;
  side: number;
  rear: number;
  height: number;
}) {
  const halfW = lotWidth / 2;
  const halfD = lotDepth / 2;
  const fontSize = Math.max(1.2, Math.min(3, lotWidth / 30));

  return (
    <group>
      {/* Lot width — along front edge */}
      <Text
        position={[0, 0.1, halfD + fontSize * 1.5]}
        fontSize={fontSize}
        color={COLORS.labelText}
        anchorX="center"
        anchorY="middle"
        rotation={[-Math.PI / 2, 0, 0]}
      >
        {`${lotWidth} ft (width)`}
      </Text>

      {/* Lot depth — along right edge */}
      <Text
        position={[halfW + fontSize * 2, 0.1, 0]}
        fontSize={fontSize}
        color={COLORS.labelText}
        anchorX="center"
        anchorY="middle"
        rotation={[-Math.PI / 2, 0, -Math.PI / 2]}
      >
        {`${lotDepth} ft (depth)`}
      </Text>

      {/* Max height — vertical label */}
      {height > 0 && (
        <Text
          position={[-halfW - fontSize * 2, height / 2, -halfD]}
          fontSize={fontSize}
          color={COLORS.labelText}
          anchorX="center"
          anchorY="middle"
        >
          {`${height} ft`}
        </Text>
      )}

      {/* Max height label at top */}
      {height > 0 && (
        <Text
          position={[0, height + fontSize, 0]}
          fontSize={fontSize * 0.8}
          color={COLORS.dimText}
          anchorX="center"
          anchorY="middle"
        >
          Max Height
        </Text>
      )}

      {/* Front setback */}
      {front > 0 && (
        <Text
          position={[0, 0.1, halfD - front / 2]}
          fontSize={fontSize * 0.7}
          color={COLORS.setbackLine}
          anchorX="center"
          anchorY="middle"
          rotation={[-Math.PI / 2, 0, 0]}
        >
          {`Front: ${front} ft`}
        </Text>
      )}

      {/* Rear setback */}
      {rear > 0 && (
        <Text
          position={[0, 0.1, -halfD + rear / 2]}
          fontSize={fontSize * 0.7}
          color={COLORS.setbackLine}
          anchorX="center"
          anchorY="middle"
          rotation={[-Math.PI / 2, 0, 0]}
        >
          {`Rear: ${rear} ft`}
        </Text>
      )}

      {/* Side setback — left */}
      {side > 0 && (
        <Text
          position={[-halfW + side / 2, 0.1, 0]}
          fontSize={fontSize * 0.7}
          color={COLORS.setbackLine}
          anchorX="center"
          anchorY="middle"
          rotation={[-Math.PI / 2, 0, -Math.PI / 2]}
        >
          {`Side: ${side} ft`}
        </Text>
      )}
    </group>
  );
}

/** Vertical height indicator line */
function HeightIndicator({
  lotWidth,
  lotDepth,
  height,
}: {
  lotWidth: number;
  lotDepth: number;
  height: number;
}) {
  if (height <= 0) return null;

  const halfW = lotWidth / 2;
  const halfD = lotDepth / 2;

  const points: [number, number, number][] = [
    [-halfW - 1, 0, -halfD],
    [-halfW - 1, height, -halfD],
  ];

  // Small ticks at top and bottom
  const tickLen = 1.5;
  const tickBottom: [number, number, number][] = [
    [-halfW - 1 - tickLen / 2, 0, -halfD],
    [-halfW - 1 + tickLen / 2, 0, -halfD],
  ];
  const tickTop: [number, number, number][] = [
    [-halfW - 1 - tickLen / 2, height, -halfD],
    [-halfW - 1 + tickLen / 2, height, -halfD],
  ];

  return (
    <group>
      <Line points={points} color={COLORS.dimText} lineWidth={1.5} />
      <Line points={tickBottom} color={COLORS.dimText} lineWidth={1.5} />
      <Line points={tickTop} color={COLORS.dimText} lineWidth={1.5} />
    </group>
  );
}

/** Lot outline border */
function LotOutline({ width, depth }: { width: number; depth: number }) {
  const hw = width / 2;
  const hd = depth / 2;
  const y = 0.03;

  const points: [number, number, number][] = [
    [-hw, y, -hd],
    [hw, y, -hd],
    [hw, y, hd],
    [-hw, y, hd],
    [-hw, y, -hd],
  ];

  return <Line points={points} color="#78716c" lineWidth={2} />;
}

// ---------------------------------------------------------------------------
// Scene (all 3D content)
// ---------------------------------------------------------------------------

function EnvelopeScene(props: EnvelopeViewerProps) {
  const { lotWidthFt, lotDepthFt, setbackFrontFt, setbackSideFt, setbackRearFt, maxHeightFt } =
    props;

  // Camera distance based on lot size
  const maxDim = Math.max(lotWidthFt, lotDepthFt, maxHeightFt);
  const camDist = maxDim * 1.3;

  // Grid size — round up to nearest 10
  const gridSize = Math.ceil(Math.max(lotWidthFt, lotDepthFt) / 10) * 10 + 20;

  return (
    <>
      {/* Lighting */}
      <ambientLight intensity={0.6} />
      <directionalLight position={[camDist, camDist, camDist]} intensity={0.8} />

      {/* Camera controls */}
      <OrbitControls
        makeDefault
        enableDamping
        dampingFactor={0.12}
        minDistance={10}
        maxDistance={camDist * 3}
        maxPolarAngle={Math.PI / 2 - 0.05} // prevent going below ground
      />

      {/* Ground grid */}
      <Grid
        args={[gridSize, gridSize]}
        cellSize={10}
        cellColor={COLORS.gridLine}
        cellThickness={0.5}
        sectionSize={50}
        sectionColor={COLORS.gridLine}
        sectionThickness={1}
        fadeDistance={camDist * 2}
        fadeStrength={1}
        position={[0, -0.01, 0]}
        infiniteGrid={false}
      />

      {/* Lot surface */}
      <LotPlane width={lotWidthFt} depth={lotDepthFt} />
      <LotOutline width={lotWidthFt} depth={lotDepthFt} />

      {/* Setback dashed outline */}
      <SetbackOutline
        lotWidth={lotWidthFt}
        lotDepth={lotDepthFt}
        front={setbackFrontFt}
        side={setbackSideFt}
        rear={setbackRearFt}
      />

      {/* Buildable envelope */}
      <BuildableEnvelope
        lotWidth={lotWidthFt}
        lotDepth={lotDepthFt}
        front={setbackFrontFt}
        side={setbackSideFt}
        rear={setbackRearFt}
        height={maxHeightFt}
      />
      <EnvelopeEdges
        lotWidth={lotWidthFt}
        lotDepth={lotDepthFt}
        front={setbackFrontFt}
        side={setbackSideFt}
        rear={setbackRearFt}
        height={maxHeightFt}
      />

      {/* Height ceiling plane */}
      <HeightPlane
        lotWidth={lotWidthFt}
        lotDepth={lotDepthFt}
        height={maxHeightFt}
      />

      {/* Height indicator line */}
      <HeightIndicator
        lotWidth={lotWidthFt}
        lotDepth={lotDepthFt}
        height={maxHeightFt}
      />

      {/* Dimension labels */}
      <DimensionLabels
        lotWidth={lotWidthFt}
        lotDepth={lotDepthFt}
        front={setbackFrontFt}
        side={setbackSideFt}
        rear={setbackRearFt}
        height={maxHeightFt}
      />
    </>
  );
}

// ---------------------------------------------------------------------------
// Main component (default export for dynamic import)
// ---------------------------------------------------------------------------

export default function EnvelopeViewer(props: EnvelopeViewerProps) {
  const {
    lotWidthFt,
    lotDepthFt,
    setbackFrontFt,
    setbackSideFt,
    setbackRearFt,
    maxHeightFt,
    buildableAreaSqft,
  } = props;

  // Validate: need positive lot dimensions to render anything useful
  const isValid = lotWidthFt > 0 && lotDepthFt > 0;

  // Compute buildable footprint for the legend
  const bw = lotWidthFt - 2 * setbackSideFt;
  const bd = lotDepthFt - setbackFrontFt - setbackRearFt;
  const computedArea = bw > 0 && bd > 0 ? bw * bd : 0;
  const displayArea = buildableAreaSqft ?? computedArea;

  // Camera position — isometric-ish view
  const maxDim = useMemo(
    () => Math.max(lotWidthFt, lotDepthFt, maxHeightFt || 35),
    [lotWidthFt, lotDepthFt, maxHeightFt],
  );
  const camDist = maxDim * 1.3;

  if (!isValid) {
    return (
      <div className="flex h-[400px] items-center justify-center rounded-lg border border-stone-200 bg-stone-50">
        <p className="text-sm text-stone-500">
          Lot dimensions required to render the 3D buildable envelope.
        </p>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {/* 3D Canvas */}
      <div className="relative h-[400px] w-full overflow-hidden rounded-lg border border-stone-200 bg-gradient-to-b from-stone-100 to-stone-50">
        <Canvas
          camera={{
            position: [camDist * 0.7, camDist * 0.6, camDist * 0.7],
            fov: 45,
            near: 0.1,
            far: camDist * 10,
          }}
          gl={{ antialias: true }}
        >
          <EnvelopeScene {...props} />
        </Canvas>

        {/* Overlay hint */}
        <div className="pointer-events-none absolute bottom-2 right-2 rounded-md bg-white/80 px-2 py-1 text-[10px] text-stone-400 backdrop-blur-sm">
          Drag to orbit / Scroll to zoom
        </div>
      </div>

      {/* Legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1 px-1 text-xs text-stone-500">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: COLORS.lotFill }} />
          Lot boundary
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-0.5 w-4"
            style={{
              backgroundImage: `repeating-linear-gradient(90deg, ${COLORS.setbackLine} 0 4px, transparent 4px 6px)`,
            }}
          />
          Setback lines
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-2.5 w-2.5 rounded-sm border"
            style={{ backgroundColor: `${COLORS.envelopeWall}33`, borderColor: COLORS.envelopeWall }}
          />
          Buildable envelope
        </span>
        {displayArea > 0 && (
          <span className="ml-auto font-medium text-stone-700">
            {displayArea.toLocaleString()} sqft buildable
          </span>
        )}
      </div>
    </div>
  );
}
