"use client";

interface SetbackDiagramProps {
  lotWidth: number;
  lotDepth: number;
  setbackFront: number;
  setbackSide: number;
  setbackRear: number;
}

export default function SetbackDiagram({ lotWidth, lotDepth, setbackFront, setbackSide, setbackRear }: SetbackDiagramProps) {
  // Scale lot to fit within a bounding box
  const maxW = 240;
  const maxH = 280;
  const scaleW = maxW / lotWidth;
  const scaleH = maxH / lotDepth;
  const scale = Math.min(scaleW, scaleH);
  const drawWidth = lotWidth * scale;
  const drawDepth = lotDepth * scale;

  // Padding for labels
  const padLeft = 12;
  const padRight = 40;
  const padTop = 20;
  const padBottom = 28;
  const svgWidth = drawWidth + padLeft + padRight;
  const svgHeight = drawDepth + padTop + padBottom;

  // Lot rectangle position
  const lotX = padLeft;
  const lotY = padTop;

  // Setback offsets (scaled)
  const sf = setbackFront * scale;
  const ss = setbackSide * scale;
  const sr = setbackRear * scale;

  // Buildable area (rear at top, front at bottom)
  const buildX = lotX + ss;
  const buildY = lotY + sr;
  const buildW = drawWidth - 2 * ss;
  const buildH = drawDepth - sf - sr;

  if (buildW <= 0 || buildH <= 0) return null;

  return (
    <div className="flex justify-center py-2">
      <svg
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="w-full max-w-xs"
        role="img"
        aria-label={`Lot diagram: ${lotWidth}ft wide by ${lotDepth}ft deep with setbacks`}
      >
        {/* Rear label */}
        <text x={lotX + drawWidth / 2} y={padTop - 6} textAnchor="middle" fontSize="9" fill="#a8a29e" fontWeight="500">
          REAR
        </text>

        {/* Street label */}
        <text x={lotX + drawWidth / 2} y={svgHeight - 2} textAnchor="middle" fontSize="9" fill="#a8a29e" fontWeight="500">
          STREET
        </text>

        {/* Lot boundary */}
        <rect
          x={lotX}
          y={lotY}
          width={drawWidth}
          height={drawDepth}
          fill="#f5f5f4"
          stroke="#a8a29e"
          strokeWidth={1.5}
        />

        {/* Buildable area */}
        <rect
          x={buildX}
          y={buildY}
          width={buildW}
          height={buildH}
          fill="#fef3c7"
          stroke="#d97706"
          strokeWidth={1}
          strokeDasharray="4 2"
          opacity={0.8}
        />

        {/* Front setback line + label */}
        {setbackFront > 0 && (
          <>
            <line x1={lotX} y1={lotY + drawDepth - sf} x2={lotX + drawWidth} y2={lotY + drawDepth - sf} stroke="#d97706" strokeWidth={0.5} strokeDasharray="3 2" />
            <text x={lotX + drawWidth + 4} y={lotY + drawDepth - sf / 2} textAnchor="start" dominantBaseline="middle" fontSize="9" fill="#b45309" fontWeight="500">
              {setbackFront}ft
            </text>
          </>
        )}

        {/* Rear setback line + label */}
        {setbackRear > 0 && (
          <>
            <line x1={lotX} y1={lotY + sr} x2={lotX + drawWidth} y2={lotY + sr} stroke="#d97706" strokeWidth={0.5} strokeDasharray="3 2" />
            <text x={lotX + drawWidth + 4} y={lotY + sr / 2} textAnchor="start" dominantBaseline="middle" fontSize="9" fill="#b45309" fontWeight="500">
              {setbackRear}ft
            </text>
          </>
        )}

        {/* Side setback lines + label */}
        {setbackSide > 0 && (
          <>
            <line x1={lotX + ss} y1={lotY} x2={lotX + ss} y2={lotY + drawDepth} stroke="#d97706" strokeWidth={0.5} strokeDasharray="3 2" />
            <line x1={lotX + drawWidth - ss} y1={lotY} x2={lotX + drawWidth - ss} y2={lotY + drawDepth} stroke="#d97706" strokeWidth={0.5} strokeDasharray="3 2" />
            <text
              x={lotX + ss / 2}
              y={lotY + drawDepth / 2}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize="9"
              fill="#b45309"
              fontWeight="500"
              transform={`rotate(-90, ${lotX + ss / 2}, ${lotY + drawDepth / 2})`}
            >
              {setbackSide}ft
            </text>
          </>
        )}

        {/* Lot width label */}
        <text x={lotX + drawWidth / 2} y={lotY + drawDepth + 14} textAnchor="middle" fontSize="10" fill="#57534e" fontWeight="500">
          {lotWidth} ft
        </text>

        {/* Lot depth label (rotated) */}
        <text
          x={lotX + drawWidth + 28}
          y={lotY + drawDepth / 2}
          textAnchor="middle"
          dominantBaseline="middle"
          fontSize="10"
          fill="#57534e"
          fontWeight="500"
          transform={`rotate(-90, ${lotX + drawWidth + 28}, ${lotY + drawDepth / 2})`}
        >
          {lotDepth} ft
        </text>

        {/* Buildable label */}
        <text x={lotX + drawWidth / 2} y={lotY + drawDepth / 2 - 6} textAnchor="middle" dominantBaseline="middle" fontSize="10" fill="#b45309" fontWeight="600">
          Buildable
        </text>
        <text x={lotX + drawWidth / 2} y={lotY + drawDepth / 2 + 8} textAnchor="middle" dominantBaseline="middle" fontSize="9" fill="#92400e">
          {Math.round(buildW / scale)} x {Math.round(buildH / scale)} ft
        </text>
      </svg>
    </div>
  );
}
