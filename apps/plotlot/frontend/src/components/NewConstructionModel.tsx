"use client";

export default function NewConstructionModel() {
  return (
    <div
      className="plotlot-motion-stage relative h-[420px] w-full overflow-hidden rounded-[36px] border border-[var(--color-steel-accent)] bg-[linear-gradient(145deg,#ffffff_0%,#f5f5f7_48%,#eaf4ff_100%)]"
      aria-label="Animated site feasibility product visual"
    >
      <style>{`
        .plotlot-motion-stage { box-shadow: rgba(0, 0, 0, 0.05) 0 0 35px 20px; }
        .plotlot-motion-glass { animation: plotlot-float 7s ease-in-out infinite; transform-origin: 50% 50%; }
        .plotlot-motion-layer-a { animation: plotlot-drift-a 8s ease-in-out infinite; transform-origin: 50% 50%; }
        .plotlot-motion-layer-b { animation: plotlot-drift-b 9s ease-in-out infinite; transform-origin: 50% 50%; }
        .plotlot-motion-scan { animation: plotlot-scan 4.8s ease-in-out infinite; }
        .plotlot-motion-pulse { animation: plotlot-pulse 2.6s ease-in-out infinite; }
        .plotlot-motion-score { animation: plotlot-score 5.2s ease-in-out infinite; transform-origin: 50% 50%; }
        .plotlot-motion-build { animation: plotlot-rise 6.4s ease-in-out infinite; transform-origin: 50% 85%; }
        @keyframes plotlot-float { 0%, 100% { transform: translate3d(0, 0, 0) rotate(-0.35deg); } 50% { transform: translate3d(0, -10px, 0) rotate(0.35deg); } }
        @keyframes plotlot-drift-a { 0%, 100% { transform: translate3d(0, 0, 0); } 50% { transform: translate3d(10px, -7px, 0); } }
        @keyframes plotlot-drift-b { 0%, 100% { transform: translate3d(0, 0, 0); } 50% { transform: translate3d(-9px, 8px, 0); } }
        @keyframes plotlot-scan { 0% { transform: translateX(-38%); opacity: 0; } 18% { opacity: .82; } 72% { opacity: .82; } 100% { transform: translateX(54%); opacity: 0; } }
        @keyframes plotlot-pulse { 0%, 100% { opacity: .32; transform: scale(0.97); } 50% { opacity: .9; transform: scale(1.04); } }
        @keyframes plotlot-score { 0%, 100% { transform: rotate(0deg) scale(1); } 50% { transform: rotate(8deg) scale(1.035); } }
        @keyframes plotlot-rise { 0%, 100% { transform: translateY(0) scaleY(1); } 50% { transform: translateY(-8px) scaleY(1.035); } }
        @media (prefers-reduced-motion: reduce) {
          .plotlot-motion-stage * { animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; }
        }
      `}</style>

      <svg className="absolute inset-0 h-full w-full" viewBox="0 0 860 560" fill="none" aria-hidden="true">
        <defs>
          <linearGradient id="feasibility-sheen" x1="131" y1="85" x2="734" y2="458" gradientUnits="userSpaceOnUse">
            <stop stopColor="#ffffff" />
            <stop offset="0.52" stopColor="#f7fbff" />
            <stop offset="1" stopColor="#e7f2ff" />
          </linearGradient>
          <linearGradient id="parcel-spectrum" x1="189" y1="164" x2="684" y2="386" gradientUnits="userSpaceOnUse">
            <stop stopColor="#00a1b3" />
            <stop offset="0.48" stopColor="#8668ff" />
            <stop offset="1" stopColor="#ed6300" />
          </linearGradient>
          <linearGradient id="scan-gradient" x1="0" y1="0" x2="1" y2="0">
            <stop stopColor="#0071e3" stopOpacity="0" />
            <stop offset="0.5" stopColor="#0071e3" stopOpacity="0.48" />
            <stop offset="1" stopColor="#0071e3" stopOpacity="0" />
          </linearGradient>
          <filter id="soft-product-shadow" x="70" y="74" width="720" height="440" filterUnits="userSpaceOnUse" colorInterpolationFilters="sRGB">
            <feDropShadow dx="0" dy="28" stdDeviation="26" floodColor="#1d1d1f" floodOpacity="0.11" />
          </filter>
          <filter id="micro-shadow" x="0" y="0" width="200%" height="200%">
            <feDropShadow dx="0" dy="10" stdDeviation="10" floodColor="#1d1d1f" floodOpacity="0.10" />
          </filter>
        </defs>

        <circle cx="610" cy="126" r="170" fill="#9fc6f4" opacity="0.16" />
        <circle cx="688" cy="420" r="180" fill="#0071e3" opacity="0.08" />
        <circle cx="250" cy="410" r="120" fill="#00a1b3" opacity="0.08" />

        <g className="plotlot-motion-glass" filter="url(#soft-product-shadow)">
          <path d="M136 128C136 107.013 153.013 90 174 90H692C712.987 90 730 107.013 730 128V412C730 432.987 712.987 450 692 450H174C153.013 450 136 432.987 136 412V128Z" fill="url(#feasibility-sheen)" stroke="#d6d6d6" strokeWidth="1.6" />
          <path d="M174 128H692V412H174V128Z" fill="#ffffff" opacity="0.46" />

          <g opacity="0.38">
            {Array.from({ length: 9 }).map((_, index) => (
              <path key={`h-${index}`} d={`M184 ${158 + index * 26}H682`} stroke="#dedfe2" strokeWidth="1" />
            ))}
            {Array.from({ length: 12 }).map((_, index) => (
              <path key={`v-${index}`} d={`M${206 + index * 42} 142V398`} stroke="#dedfe2" strokeWidth="1" />
            ))}
          </g>

          <g className="plotlot-motion-layer-a">
            <path d="M205 216L332 165L548 196L657 318L431 391L235 333Z" fill="url(#parcel-spectrum)" fillOpacity="0.09" stroke="url(#parcel-spectrum)" strokeWidth="4.5" strokeLinejoin="round" />
            <path d="M262 237L354 204L512 226L591 307L432 355L281 315Z" stroke="#0071e3" strokeWidth="2.5" strokeDasharray="12 12" strokeLinecap="round" strokeLinejoin="round">
              <animate attributeName="stroke-dashoffset" from="0" to="-48" dur="3.8s" repeatCount="indefinite" />
            </path>
          </g>

          <g className="plotlot-motion-layer-b">
            <path d="M326 283C352 239 463 235 518 274C572 313 517 352 427 349C340 346 295 336 326 283Z" fill="#00a1b3" fillOpacity="0.16" stroke="#00a1b3" strokeWidth="2.7" />
            <path d="M351 282C374 257 452 255 490 278C530 302 492 327 428 325C365 323 324 312 351 282Z" fill="#9fc6f4" fillOpacity="0.28" />
          </g>

          <g className="plotlot-motion-build" filter="url(#micro-shadow)">
            <path d="M474 258L578 222L664 258L556 301Z" fill="#ffffff" stroke="#d6d6d6" strokeWidth="2" />
            <path d="M474 258V174L578 139V222Z" fill="#fbfbfd" stroke="#d6d6d6" strokeWidth="2" />
            <path d="M578 139L664 176V258L578 222Z" fill="#e8e8ed" stroke="#d6d6d6" strokeWidth="2" />
            <path d="M506 199L553 184M506 224L553 210M602 181L642 198M602 207L642 224" stroke="#ffffff" strokeWidth="4" strokeLinecap="round" opacity="0.92" />
          </g>

          <g className="plotlot-motion-scan">
            <rect x="222" y="139" width="86" height="268" rx="43" fill="url(#scan-gradient)" opacity="0.75" />
            <path d="M265 146V398" stroke="#0071e3" strokeOpacity="0.28" strokeWidth="1.5" />
          </g>

          <g className="plotlot-motion-score" transform="translate(602 344)">
            <path d="M0 54A54 54 0 1 0 0 -54" stroke="#0071e3" strokeWidth="9" strokeLinecap="round" opacity="0.78" />
            <path d="M0 54A54 54 0 0 0 51 17" stroke="#00a1b3" strokeWidth="9" strokeLinecap="round" opacity="0.48" />
          </g>

          <g className="plotlot-motion-pulse">
            <circle cx="241" cy="216" r="7" fill="#0071e3" />
            <circle cx="241" cy="216" r="18" stroke="#0071e3" strokeOpacity="0.22" strokeWidth="2" />
            <circle cx="548" cy="196" r="7" fill="#ed6300" />
            <circle cx="548" cy="196" r="18" stroke="#ed6300" strokeOpacity="0.22" strokeWidth="2" />
          </g>
        </g>
      </svg>

      <div className="pointer-events-none absolute left-5 top-5 rounded-[28px] bg-white/84 px-4 py-3 text-[12px] leading-tight text-[var(--color-cloud-mist)] shadow-[var(--shadow-subtle)] backdrop-blur-xl">
        <div className="text-[13px] font-semibold tracking-[-0.16px] text-[var(--color-midnight-graphite)]">Site feasibility lens</div>
        <div>zoning, envelope, yield, risk</div>
      </div>
      <div className="pointer-events-none absolute bottom-5 right-5 flex items-center gap-3 rounded-[28px] bg-[var(--color-midnight-graphite)] px-4 py-3 text-white shadow-[0_18px_50px_rgba(0,0,0,0.12)]">
        <span className="h-3 w-3 rounded-full bg-[var(--color-sky-teal)]" />
        <span className="text-[13px] font-semibold tracking-[-0.16px]">84 feasible</span>
      </div>
    </div>
  );
}
