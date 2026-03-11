"use client";

import { useMemo } from "react";
import * as THREE from "three";

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface BuildingModelProps {
  footprintWidth: number;
  footprintDepth: number;
  maxStories: number;
  maxHeightFt: number;
  maxLotCoveragePct: number;
  far: number;
  lotSizeSqft: number;
  propertyType: string;
  maxUnits: number;
  parkingPerUnit: number;
  positionX: number;
  positionZ: number;
}

// ---------------------------------------------------------------------------
// Procedural texture generators (CanvasTexture — no external assets)
// ---------------------------------------------------------------------------

function createSidingTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;

  // Warm beige base
  ctx.fillStyle = "#E8DCC8";
  ctx.fillRect(0, 0, 512, 512);

  // Horizontal lap siding
  const lapH = 18;
  for (let y = 0; y < 512; y += lapH) {
    // Shadow at top of each lap
    ctx.fillStyle = "rgba(0,0,0,0.07)";
    ctx.fillRect(0, y, 512, 2);
    // Highlight at bottom
    ctx.fillStyle = "rgba(255,255,255,0.05)";
    ctx.fillRect(0, y + lapH - 2, 512, 1);
  }

  // Subtle wood grain variation
  for (let x = 0; x < 512; x += 3) {
    ctx.fillStyle = `rgba(0,0,0,${Math.random() * 0.015})`;
    ctx.fillRect(x, 0, 1, 512);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function createShingleTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#5A534A";
  ctx.fillRect(0, 0, 512, 512);

  const shingleH = 20;
  const shingleW = 36;
  for (let row = 0; row < 512 / shingleH + 1; row++) {
    const y = row * shingleH;
    const offset = (row % 2) * (shingleW / 2);
    for (let x = -shingleW + offset; x < 512 + shingleW; x += shingleW) {
      const shade = 50 + Math.random() * 35;
      ctx.fillStyle = `rgb(${shade + 28}, ${shade + 22}, ${shade + 12})`;
      ctx.fillRect(x + 1, y + 1, shingleW - 2, shingleH - 1);
      ctx.fillStyle = "rgba(0,0,0,0.18)";
      ctx.fillRect(x, y + shingleH - 2, shingleW, 2);
    }
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function createGrassTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#3D7A4A";
  ctx.fillRect(0, 0, 256, 256);

  for (let i = 0; i < 3000; i++) {
    const x = Math.random() * 256;
    const y = Math.random() * 256;
    const g = 70 + Math.random() * 60;
    ctx.fillStyle = `rgba(${25 + Math.random() * 25}, ${g + 40}, ${20 + Math.random() * 20}, 0.35)`;
    ctx.fillRect(x, y, 1, 1 + Math.random() * 3);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(6, 6);
  return tex;
}

function createConcreteTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#B5AFA5";
  ctx.fillRect(0, 0, 256, 256);

  for (let i = 0; i < 400; i++) {
    ctx.fillStyle = `rgba(0,0,0,${Math.random() * 0.04})`;
    ctx.fillRect(Math.random() * 256, Math.random() * 256, 2 + Math.random() * 3, 2 + Math.random() * 3);
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  return tex;
}

function createStuccoTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 256;
  canvas.height = 256;
  const ctx = canvas.getContext("2d")!;

  ctx.fillStyle = "#E8E2D8";
  ctx.fillRect(0, 0, 256, 256);

  // Stucco bumps
  for (let i = 0; i < 1500; i++) {
    const x = Math.random() * 256;
    const y = Math.random() * 256;
    const r = 0.5 + Math.random() * 1.5;
    ctx.fillStyle = `rgba(${Math.random() > 0.5 ? 255 : 0},${Math.random() > 0.5 ? 255 : 0},${Math.random() > 0.5 ? 255 : 0},${Math.random() * 0.03})`;
    ctx.beginPath();
    ctx.arc(x, y, r, 0, Math.PI * 2);
    ctx.fill();
  }

  const tex = new THREE.CanvasTexture(canvas);
  tex.wrapS = THREE.RepeatWrapping;
  tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(3, 3);
  return tex;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const STORY_HEIGHT = 10;
const FOUNDATION_H = 1.5;

// ---------------------------------------------------------------------------
// Textured Wall component
// ---------------------------------------------------------------------------

function TexturedWalls({
  w, d, h, stories, isCommercial,
}: {
  w: number; d: number; h: number; stories: number; isCommercial: boolean;
}) {
  const sidingTex = useMemo(() => {
    const tex = isCommercial ? createStuccoTexture() : createSidingTexture();
    // Scale texture to building size
    tex.repeat.set(w / 12, h / 10);
    return tex;
  }, [w, h, isCommercial]);

  const sideSidingTex = useMemo(() => {
    const tex = isCommercial ? createStuccoTexture() : createSidingTexture();
    tex.repeat.set(d / 12, h / 10);
    return tex;
  }, [d, h, isCommercial]);

  const wt = 0.6; // wall thickness

  return (
    <group>
      {/* Foundation */}
      <mesh position={[0, FOUNDATION_H / 2, 0]} castShadow>
        <boxGeometry args={[w + 0.4, FOUNDATION_H, d + 0.4]} />
        <meshStandardMaterial color="#8A8278" roughness={0.95} />
      </mesh>

      {/* Front wall */}
      <mesh position={[0, FOUNDATION_H + h / 2, d / 2]} castShadow>
        <boxGeometry args={[w, h, wt]} />
        <meshStandardMaterial map={sidingTex} roughness={0.8} metalness={0.02} />
      </mesh>
      {/* Back wall */}
      <mesh position={[0, FOUNDATION_H + h / 2, -d / 2]} castShadow>
        <boxGeometry args={[w, h, wt]} />
        <meshStandardMaterial map={sidingTex} roughness={0.8} metalness={0.02} />
      </mesh>
      {/* Left wall */}
      <mesh position={[-w / 2, FOUNDATION_H + h / 2, 0]} castShadow>
        <boxGeometry args={[wt, h, d]} />
        <meshStandardMaterial map={sideSidingTex} roughness={0.8} metalness={0.02} />
      </mesh>
      {/* Right wall */}
      <mesh position={[w / 2, FOUNDATION_H + h / 2, 0]} castShadow>
        <boxGeometry args={[wt, h, d]} />
        <meshStandardMaterial map={sideSidingTex} roughness={0.8} metalness={0.02} />
      </mesh>

      {/* Floor slabs */}
      {Array.from({ length: stories }, (_, i) => (
        <mesh key={i} position={[0, FOUNDATION_H + (i + 1) * STORY_HEIGHT, 0]}>
          <boxGeometry args={[w - 0.4, 0.35, d - 0.4]} />
          <meshStandardMaterial color="#DDD8D0" roughness={0.9} />
        </mesh>
      ))}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Textured Gable Roof with shingle pattern + fascia
// ---------------------------------------------------------------------------

function TexturedGableRoof({ w, d, h }: { w: number; d: number; h: number }) {
  const overhang = 2;
  const peakH = Math.min(w * 0.25, 8);
  const rw = w + overhang * 2;
  const rd = d + overhang * 2;
  const baseY = FOUNDATION_H + h;

  const shingleTex = useMemo(() => {
    const tex = createShingleTexture();
    tex.repeat.set(rw / 8, (peakH + 2) / 6);
    return tex;
  }, [rw, peakH]);

  const roofGeo = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    const hw = rw / 2;
    const hd = rd / 2;
    const vertices = new Float32Array([
      // Left slope
      -hw, baseY, hd, 0, baseY + peakH, hd, -hw, baseY, -hd,
      0, baseY + peakH, hd, 0, baseY + peakH, -hd, -hw, baseY, -hd,
      // Right slope
      hw, baseY, hd, hw, baseY, -hd, 0, baseY + peakH, hd,
      0, baseY + peakH, hd, hw, baseY, -hd, 0, baseY + peakH, -hd,
      // Front gable
      -hw, baseY, hd, hw, baseY, hd, 0, baseY + peakH, hd,
      // Back gable
      -hw, baseY, -hd, 0, baseY + peakH, -hd, hw, baseY, -hd,
    ]);

    // UVs for texture mapping
    const uvs = new Float32Array([
      0, 0, 0.5, 1, 1, 0,   0.5, 1, 0.5, 1, 1, 0,
      0, 0, 1, 0, 0.5, 1,   0.5, 1, 1, 0, 0.5, 1,
      0, 0, 1, 0, 0.5, 1,
      0, 0, 0.5, 1, 1, 0,
    ]);

    geo.setAttribute("position", new THREE.BufferAttribute(vertices, 3));
    geo.setAttribute("uv", new THREE.BufferAttribute(uvs, 2));
    geo.computeVertexNormals();
    return geo;
  }, [rw, rd, baseY, peakH]);

  return (
    <group>
      <mesh geometry={roofGeo} castShadow>
        <meshStandardMaterial map={shingleTex} roughness={0.85} side={THREE.DoubleSide} />
      </mesh>

      {/* Ridge cap */}
      <mesh position={[0, baseY + peakH + 0.15, 0]}>
        <boxGeometry args={[0.8, 0.3, rd]} />
        <meshStandardMaterial color="#4A4440" roughness={0.8} />
      </mesh>

      {/* Fascia board — front */}
      <mesh position={[0, baseY - 0.2, rd / 2 + 0.1]}>
        <boxGeometry args={[rw, 0.6, 0.3]} />
        <meshStandardMaterial color="#F0EBE0" roughness={0.7} />
      </mesh>
      {/* Fascia board — back */}
      <mesh position={[0, baseY - 0.2, -rd / 2 - 0.1]}>
        <boxGeometry args={[rw, 0.6, 0.3]} />
        <meshStandardMaterial color="#F0EBE0" roughness={0.7} />
      </mesh>

      {/* Gutter — front */}
      <mesh position={[0, baseY - 0.5, rd / 2 + 0.3]} castShadow>
        <boxGeometry args={[rw - 0.5, 0.25, 0.25]} />
        <meshStandardMaterial color="#AAAAAA" roughness={0.4} metalness={0.4} />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Flat Roof with parapet
// ---------------------------------------------------------------------------

function TexturedFlatRoof({ w, d, h }: { w: number; d: number; h: number }) {
  const baseY = FOUNDATION_H + h;
  const parapetH = 2.5;

  return (
    <group>
      <mesh position={[0, baseY + 0.15, 0]}>
        <boxGeometry args={[w + 0.5, 0.3, d + 0.5]} />
        <meshStandardMaterial color="#888580" roughness={0.95} />
      </mesh>
      {/* Parapet — all 4 sides */}
      {[
        { pos: [0, baseY + parapetH / 2, d / 2 + 0.25] as const, size: [w + 0.8, parapetH, 0.5] as const },
        { pos: [0, baseY + parapetH / 2, -d / 2 - 0.25] as const, size: [w + 0.8, parapetH, 0.5] as const },
        { pos: [-w / 2 - 0.25, baseY + parapetH / 2, 0] as const, size: [0.5, parapetH, d + 0.3] as const },
        { pos: [w / 2 + 0.25, baseY + parapetH / 2, 0] as const, size: [0.5, parapetH, d + 0.3] as const },
      ].map((p, i) => (
        <mesh key={i} position={p.pos}>
          <boxGeometry args={p.size} />
          <meshStandardMaterial color="#9A9590" roughness={0.85} />
        </mesh>
      ))}
      {/* Coping — parapet cap */}
      <mesh position={[0, baseY + parapetH + 0.1, d / 2 + 0.25]}>
        <boxGeometry args={[w + 1.2, 0.2, 0.8]} />
        <meshStandardMaterial color="#B5B0A8" roughness={0.6} metalness={0.1} />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Recessed window with mullions, sill, and frame
// ---------------------------------------------------------------------------

function DetailedWindow({
  x, y, z, rotY, winW, winH,
}: {
  x: number; y: number; z: number; rotY: number; winW: number; winH: number;
}) {
  const frameD = 0.2;
  const mullion = 0.15;

  return (
    <group position={[x, y, z]} rotation={[0, rotY, 0]}>
      {/* Window recess (dark shadow) */}
      <mesh position={[0, 0, -0.15]}>
        <boxGeometry args={[winW + 0.3, winH + 0.3, 0.4]} />
        <meshStandardMaterial color="#3A3530" roughness={0.95} />
      </mesh>

      {/* Glass panes (4 panes) */}
      <mesh position={[0, 0, 0.02]}>
        <planeGeometry args={[winW, winH]} />
        <meshPhysicalMaterial
          color="#6EAED4"
          roughness={0.1}
          metalness={0.3}
          transmission={0.2}
          transparent
          opacity={0.75}
        />
      </mesh>

      {/* White frame — outer */}
      <mesh position={[0, 0, 0.05]}>
        <planeGeometry args={[winW + 0.3, winH + 0.3]} />
        <meshStandardMaterial color="#F5F2EC" roughness={0.5} />
      </mesh>
      {/* Cut out center (glass visible through frame) — rendered as 4 frame bars */}
      {/* Top bar */}
      <mesh position={[0, winH / 2, 0.08]}>
        <boxGeometry args={[winW + 0.3, frameD, 0.08]} />
        <meshStandardMaterial color="#F5F2EC" roughness={0.5} />
      </mesh>
      {/* Bottom bar */}
      <mesh position={[0, -winH / 2, 0.08]}>
        <boxGeometry args={[winW + 0.3, frameD, 0.08]} />
        <meshStandardMaterial color="#F5F2EC" roughness={0.5} />
      </mesh>
      {/* Left bar */}
      <mesh position={[-winW / 2, 0, 0.08]}>
        <boxGeometry args={[frameD, winH + 0.3, 0.08]} />
        <meshStandardMaterial color="#F5F2EC" roughness={0.5} />
      </mesh>
      {/* Right bar */}
      <mesh position={[winW / 2, 0, 0.08]}>
        <boxGeometry args={[frameD, winH + 0.3, 0.08]} />
        <meshStandardMaterial color="#F5F2EC" roughness={0.5} />
      </mesh>

      {/* Horizontal mullion (center cross) */}
      <mesh position={[0, 0, 0.08]}>
        <boxGeometry args={[winW, mullion, 0.06]} />
        <meshStandardMaterial color="#F5F2EC" roughness={0.5} />
      </mesh>
      {/* Vertical mullion */}
      <mesh position={[0, 0, 0.08]}>
        <boxGeometry args={[mullion, winH, 0.06]} />
        <meshStandardMaterial color="#F5F2EC" roughness={0.5} />
      </mesh>

      {/* Sill */}
      <mesh position={[0, -winH / 2 - 0.2, 0.2]}>
        <boxGeometry args={[winW + 0.6, 0.15, 0.4]} />
        <meshStandardMaterial color="#E8E4DC" roughness={0.6} />
      </mesh>
    </group>
  );
}

function WindowGrid({ w, d, h, stories }: { w: number; d: number; h: number; stories: number }) {
  const winW = 3;
  const winH = 4.5;

  const positions: { x: number; y: number; z: number; rotY: number }[] = [];

  for (let floor = 0; floor < stories; floor++) {
    const baseY = FOUNDATION_H + floor * STORY_HEIGHT + 4;

    // Front + back
    const spacing = Math.max(7, w / Math.max(Math.floor(w / 7), 1));
    for (let wx = -w / 2 + spacing / 2; wx < w / 2; wx += spacing) {
      positions.push({ x: wx, y: baseY, z: d / 2 + 0.3, rotY: 0 });
      positions.push({ x: wx, y: baseY, z: -d / 2 - 0.3, rotY: Math.PI });
    }

    // Sides
    const sideSpacing = Math.max(9, d / Math.max(Math.floor(d / 9), 1));
    for (let wz = -d / 2 + sideSpacing / 2; wz < d / 2; wz += sideSpacing) {
      positions.push({ x: -w / 2 - 0.3, y: baseY, z: wz, rotY: -Math.PI / 2 });
      positions.push({ x: w / 2 + 0.3, y: baseY, z: wz, rotY: Math.PI / 2 });
    }
  }

  return (
    <group>
      {positions.map((p, i) => (
        <DetailedWindow key={i} x={p.x} y={p.y} z={p.z} rotY={p.rotY} winW={winW} winH={winH} />
      ))}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Front door with frame, panel detail, and handle
// ---------------------------------------------------------------------------

function DetailedFrontDoor({ x, d }: { x: number; d: number }) {
  const dw = 3.5;
  const dh = 7.5;
  const baseY = FOUNDATION_H + dh / 2;
  const z = d / 2 + 0.35;

  return (
    <group position={[x, 0, 0]}>
      {/* Door frame recess */}
      <mesh position={[0, baseY, z - 0.1]}>
        <boxGeometry args={[dw + 0.8, dh + 0.4, 0.4]} />
        <meshStandardMaterial color="#3A3530" roughness={0.9} />
      </mesh>

      {/* Door panel */}
      <mesh position={[0, baseY, z]}>
        <boxGeometry args={[dw, dh, 0.15]} />
        <meshStandardMaterial color="#5C3317" roughness={0.55} />
      </mesh>

      {/* Panel insets (2 rectangles) */}
      <mesh position={[0, baseY + dh * 0.18, z + 0.08]}>
        <boxGeometry args={[dw * 0.65, dh * 0.3, 0.04]} />
        <meshStandardMaterial color="#4A2810" roughness={0.6} />
      </mesh>
      <mesh position={[0, baseY - dh * 0.18, z + 0.08]}>
        <boxGeometry args={[dw * 0.65, dh * 0.3, 0.04]} />
        <meshStandardMaterial color="#4A2810" roughness={0.6} />
      </mesh>

      {/* Door handle */}
      <mesh position={[dw * 0.35, baseY - 0.5, z + 0.12]}>
        <sphereGeometry args={[0.18, 8, 8]} />
        <meshStandardMaterial color="#C4A862" roughness={0.3} metalness={0.7} />
      </mesh>

      {/* White frame trim */}
      <mesh position={[0, baseY + dh / 2 + 0.15, z + 0.04]}>
        <boxGeometry args={[dw + 0.5, 0.3, 0.1]} />
        <meshStandardMaterial color="#F0EBE0" roughness={0.5} />
      </mesh>

      {/* Transom window above door */}
      <mesh position={[0, baseY + dh / 2 + 0.6, z + 0.02]}>
        <planeGeometry args={[dw - 0.3, 1]} />
        <meshPhysicalMaterial color="#6EAED4" roughness={0.1} metalness={0.3} transparent opacity={0.7} />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Garage door with ribbed panels and window row
// ---------------------------------------------------------------------------

function DetailedGarageDoor({ w, d, parkingPerUnit }: { w: number; d: number; parkingPerUnit: number }) {
  if (parkingPerUnit < 1.5) return null;
  const gw = 16;
  const gh = 8;
  const baseY = FOUNDATION_H + gh / 2;
  const z = d / 2 + 0.35;
  const panels = 5;

  return (
    <group position={[-w / 4, 0, 0]}>
      {/* Opening recess */}
      <mesh position={[0, baseY, z - 0.15]}>
        <boxGeometry args={[gw + 0.5, gh + 0.3, 0.4]} />
        <meshStandardMaterial color="#3A3530" roughness={0.95} />
      </mesh>

      {/* Main panel */}
      <mesh position={[0, baseY, z]}>
        <boxGeometry args={[gw, gh, 0.1]} />
        <meshStandardMaterial color="#D4CFC5" roughness={0.75} />
      </mesh>

      {/* Horizontal ribs */}
      {Array.from({ length: panels }, (_, i) => {
        const panelY = baseY - gh / 2 + (i + 0.5) * (gh / panels);
        return (
          <group key={i}>
            <mesh position={[0, panelY + gh / panels / 2 - 0.1, z + 0.06]}>
              <boxGeometry args={[gw - 0.3, 0.15, 0.04]} />
              <meshStandardMaterial color="#C0BBB0" roughness={0.8} />
            </mesh>
          </group>
        );
      })}

      {/* Top row of small windows */}
      {[-5, -2.5, 0, 2.5, 5].map((wx, i) => (
        <mesh key={i} position={[wx, baseY + gh / 2 - gh / panels / 2, z + 0.08]}>
          <planeGeometry args={[2.2, gh / panels * 0.6]} />
          <meshPhysicalMaterial color="#6EAED4" roughness={0.15} metalness={0.2} transparent opacity={0.65} />
        </mesh>
      ))}

      {/* Frame trim */}
      <mesh position={[0, baseY + gh / 2 + 0.15, z + 0.04]}>
        <boxGeometry args={[gw + 0.3, 0.3, 0.08]} />
        <meshStandardMaterial color="#F0EBE0" roughness={0.5} />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Porch with steps, columns, railings, and overhang
// ---------------------------------------------------------------------------

function DetailedPorch({ w, d }: { w: number; d: number }) {
  const pw = 8;
  const pd = 5;
  const ph = 8;
  const stepsN = 3;
  const stepH = FOUNDATION_H / stepsN;
  const stepD = 1;
  const cx = w * 0.15;

  return (
    <group position={[cx, 0, d / 2]}>
      {/* Steps */}
      {Array.from({ length: stepsN }, (_, i) => (
        <mesh key={i} position={[0, (i + 0.5) * stepH, pd + (stepsN - i) * stepD]} castShadow receiveShadow>
          <boxGeometry args={[pw * 0.5, stepH, stepD]} />
          <meshStandardMaterial color="#B5AFA5" roughness={0.9} />
        </mesh>
      ))}

      {/* Porch platform */}
      <mesh position={[0, FOUNDATION_H, pd / 2]} receiveShadow>
        <boxGeometry args={[pw, 0.4, pd + 1]} />
        <meshStandardMaterial color="#A08060" roughness={0.75} />
      </mesh>

      {/* Columns (4) */}
      {[-pw / 2 + 0.6, -pw / 6, pw / 6, pw / 2 - 0.6].map((colX, i) => (
        <group key={i}>
          {/* Column shaft */}
          <mesh position={[colX, FOUNDATION_H + ph / 2, pd - 0.3]} castShadow>
            <boxGeometry args={[0.5, ph, 0.5]} />
            <meshStandardMaterial color="#F0EBE0" roughness={0.5} />
          </mesh>
          {/* Column base */}
          <mesh position={[colX, FOUNDATION_H + 0.3, pd - 0.3]}>
            <boxGeometry args={[0.8, 0.6, 0.8]} />
            <meshStandardMaterial color="#F0EBE0" roughness={0.5} />
          </mesh>
          {/* Column capital */}
          <mesh position={[colX, FOUNDATION_H + ph - 0.15, pd - 0.3]}>
            <boxGeometry args={[0.8, 0.3, 0.8]} />
            <meshStandardMaterial color="#F0EBE0" roughness={0.5} />
          </mesh>
        </group>
      ))}

      {/* Railing — horizontal top rail */}
      <mesh position={[0, FOUNDATION_H + 3, pd - 0.3]}>
        <boxGeometry args={[pw, 0.15, 0.15]} />
        <meshStandardMaterial color="#F0EBE0" roughness={0.5} />
      </mesh>
      {/* Railing — balusters */}
      {Array.from({ length: Math.floor(pw / 0.8) }, (_, i) => (
        <mesh key={i} position={[-pw / 2 + 0.6 + i * 0.8, FOUNDATION_H + 1.5, pd - 0.3]}>
          <boxGeometry args={[0.1, 3, 0.1]} />
          <meshStandardMaterial color="#F0EBE0" roughness={0.5} />
        </mesh>
      ))}

      {/* Porch roof overhang */}
      <mesh position={[0, FOUNDATION_H + ph + 0.15, pd / 2]} castShadow>
        <boxGeometry args={[pw + 1.5, 0.35, pd + 2]} />
        <meshStandardMaterial color="#E8E2D8" roughness={0.7} />
      </mesh>
    </group>
  );
}

// ---------------------------------------------------------------------------
// Storefront canopy for commercial
// ---------------------------------------------------------------------------

function StorefrontCanopy({ w, d }: { w: number; d: number }) {
  const canopyW = w * 0.85;
  const canopyD = 4;
  const canopyY = FOUNDATION_H + 10;

  return (
    <group>
      {/* Canopy slab */}
      <mesh position={[0, canopyY, d / 2 + canopyD / 2]} castShadow>
        <boxGeometry args={[canopyW, 0.4, canopyD]} />
        <meshStandardMaterial color="#6B7280" roughness={0.6} metalness={0.3} />
      </mesh>
      {/* Support brackets */}
      {[-canopyW / 3, 0, canopyW / 3].map((bx, i) => (
        <mesh key={i} position={[bx, canopyY - 0.5, d / 2 + 0.3]}>
          <boxGeometry args={[0.3, 1, 0.3]} />
          <meshStandardMaterial color="#555555" roughness={0.5} metalness={0.5} />
        </mesh>
      ))}
    </group>
  );
}

// ---------------------------------------------------------------------------
// Ground surfaces
// ---------------------------------------------------------------------------

function TexturedGround({ lotW, lotD }: { lotW: number; lotD: number }) {
  const grassTex = useMemo(() => createGrassTexture(), []);

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[0, -0.01, 0]} receiveShadow>
      <planeGeometry args={[lotW + 24, lotD + 24]} />
      <meshStandardMaterial map={grassTex} roughness={0.92} />
    </mesh>
  );
}

function TexturedDriveway({ w, d }: { w: number; d: number }) {
  const concreteTex = useMemo(() => createConcreteTexture(), []);
  const driveW = 12;
  const driveD = 14;

  return (
    <group>
      {/* Main driveway */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[-w / 4, 0.02, d / 2 + driveD / 2]} receiveShadow>
        <planeGeometry args={[driveW, driveD]} />
        <meshStandardMaterial map={concreteTex} roughness={0.88} />
      </mesh>
      {/* Driveway apron (wider at street) */}
      <mesh rotation={[-Math.PI / 2, 0, 0]} position={[-w / 4, 0.02, d / 2 + driveD + 2]} receiveShadow>
        <planeGeometry args={[driveW + 3, 4]} />
        <meshStandardMaterial map={concreteTex} roughness={0.88} />
      </mesh>
    </group>
  );
}

function Walkway({ w, d }: { w: number; d: number }) {
  const concreteTex = useMemo(() => createConcreteTexture(), []);

  return (
    <mesh rotation={[-Math.PI / 2, 0, 0]} position={[w * 0.15, 0.02, d / 2 + 5]} receiveShadow>
      <planeGeometry args={[3.5, 10]} />
      <meshStandardMaterial map={concreteTex} roughness={0.9} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Enhanced tree with multi-sphere canopy
// ---------------------------------------------------------------------------

function DetailedTree({ x, z, scale: s = 1 }: { x: number; z: number; scale?: number }) {
  const trunkH = 5 * s;
  const canopyR = 3.5 * s;

  return (
    <group position={[x, 0, z]}>
      {/* Trunk */}
      <mesh position={[0, trunkH / 2, 0]} castShadow>
        <cylinderGeometry args={[0.25 * s, 0.4 * s, trunkH, 8]} />
        <meshStandardMaterial color="#6B4226" roughness={0.9} />
      </mesh>
      {/* Canopy — main sphere */}
      <mesh position={[0, trunkH + canopyR * 0.6, 0]} castShadow>
        <sphereGeometry args={[canopyR, 10, 10]} />
        <meshStandardMaterial color="#2D6A2E" roughness={0.92} />
      </mesh>
      {/* Secondary canopy spheres for fullness */}
      <mesh position={[canopyR * 0.4, trunkH + canopyR * 0.3, canopyR * 0.3]} castShadow>
        <sphereGeometry args={[canopyR * 0.7, 8, 8]} />
        <meshStandardMaterial color="#358535" roughness={0.92} />
      </mesh>
      <mesh position={[-canopyR * 0.3, trunkH + canopyR * 0.5, -canopyR * 0.2]} castShadow>
        <sphereGeometry args={[canopyR * 0.6, 8, 8]} />
        <meshStandardMaterial color="#2A7A2C" roughness={0.92} />
      </mesh>
    </group>
  );
}

// Foundation bushes/shrubs
function Shrub({ x, z }: { x: number; z: number }) {
  return (
    <mesh position={[x, FOUNDATION_H * 0.6, z]} castShadow>
      <sphereGeometry args={[1.2, 8, 6]} />
      <meshStandardMaterial color="#3A8240" roughness={0.95} />
    </mesh>
  );
}

// ---------------------------------------------------------------------------
// Main BuildingModel component
// ---------------------------------------------------------------------------

export default function BuildingModel(props: BuildingModelProps) {
  const {
    footprintWidth, footprintDepth,
    maxStories, maxHeightFt,
    maxLotCoveragePct, far, lotSizeSqft,
    propertyType, maxUnits, parkingPerUnit,
    positionX, positionZ,
  } = props;

  // Compute zoning-constrained dimensions
  const buildableArea = footprintWidth * footprintDepth;
  const coverageLimit = maxLotCoveragePct > 0 ? (maxLotCoveragePct / 100) * lotSizeSqft : Infinity;
  const footprintArea = Math.min(buildableArea, coverageLimit);
  const scaleFactor = footprintArea < buildableArea ? Math.sqrt(footprintArea / buildableArea) : 1;

  const w = footprintWidth * scaleFactor;
  const d = footprintDepth * scaleFactor;
  const stories = Math.max(1, Math.min(maxStories || 2, Math.floor(maxHeightFt / STORY_HEIGHT)));

  let effectiveStories = stories;
  if (far > 0 && lotSizeSqft > 0) {
    const maxFloorArea = far * lotSizeSqft;
    effectiveStories = Math.min(stories, Math.max(1, Math.floor(maxFloorArea / (w * d))));
  }

  const buildingHeight = effectiveStories * STORY_HEIGHT;
  const pt = (propertyType || "").toLowerCase();
  const isCommercial = pt === "commercial" || (pt === "commercial_mf" && maxUnits <= 0);
  const isMultifamily = maxUnits >= 3 && !isCommercial;
  const isDuplex = maxUnits === 2;
  const isSFR = !isCommercial && !isMultifamily && !isDuplex;

  const lotW = footprintWidth + 12;
  const lotD = footprintDepth + 12;

  return (
    <group position={[positionX, 0, positionZ]}>
      {/* Ground */}
      <TexturedGround lotW={lotW} lotD={lotD} />

      {/* Building walls with procedural siding texture */}
      <TexturedWalls w={w} d={d} h={buildingHeight} stories={effectiveStories} isCommercial={isCommercial} />

      {/* Windows with mullions, frames, sills */}
      <WindowGrid w={w} d={d} h={buildingHeight} stories={effectiveStories} />

      {/* Roof */}
      {isSFR || isDuplex ? (
        <TexturedGableRoof w={w} d={d} h={buildingHeight} />
      ) : (
        <TexturedFlatRoof w={w} d={d} h={buildingHeight} />
      )}

      {/* SFR features */}
      {isSFR && (
        <>
          <DetailedFrontDoor x={w * 0.15} d={d} />
          <DetailedGarageDoor w={w} d={d} parkingPerUnit={parkingPerUnit} />
          <DetailedPorch w={w} d={d} />
          <TexturedDriveway w={w} d={d} />
          <Walkway w={w} d={d} />
          {/* Foundation shrubs */}
          <Shrub x={w / 4} z={d / 2 + 1} />
          <Shrub x={w / 3} z={d / 2 + 1.5} />
          <Shrub x={-w / 6} z={d / 2 + 1} />
          <Shrub x={w / 2 - 1.5} z={0} />
          <Shrub x={-w / 2 + 1.5} z={0} />
        </>
      )}

      {/* Duplex */}
      {isDuplex && (
        <>
          <DetailedFrontDoor x={-w / 4} d={d} />
          <DetailedFrontDoor x={w / 4} d={d} />
          <TexturedDriveway w={w} d={d} />
          <Walkway w={w} d={d} />
          {/* Unit division line */}
          <mesh position={[0, FOUNDATION_H + buildingHeight / 2, d / 2 + 0.35]}>
            <boxGeometry args={[0.15, buildingHeight, 0.05]} />
            <meshStandardMaterial color="#8A8278" roughness={0.8} />
          </mesh>
        </>
      )}

      {/* Multifamily */}
      {isMultifamily && (
        <>
          <DetailedFrontDoor x={0} d={d} />
          <TexturedDriveway w={w} d={d} />
          <Walkway w={w} d={d} />
        </>
      )}

      {/* Commercial */}
      {isCommercial && (
        <>
          <StorefrontCanopy w={w} d={d} />
          <DetailedFrontDoor x={0} d={d} />
          <TexturedDriveway w={w} d={d} />
        </>
      )}

      {/* Trees */}
      <DetailedTree x={-lotW / 2 + 4} z={-lotD / 2 + 4} />
      <DetailedTree x={lotW / 2 - 4} z={-lotD / 2 + 4} />
      <DetailedTree x={lotW / 2 - 3} z={lotD / 2 - 6} scale={0.8} />
      <DetailedTree x={-lotW / 2 + 5} z={lotD / 2 - 4} scale={0.9} />
    </group>
  );
}
