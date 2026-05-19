"use client";

import { useRef } from "react";
import { motion, type Variants } from "framer-motion";
import gsap from "gsap";
import { useGSAP } from "@gsap/react";
import { ScrollTrigger } from "gsap/ScrollTrigger";

gsap.registerPlugin(useGSAP, ScrollTrigger);

const lineDraw: Variants = {
  hidden: { pathLength: 0, opacity: 0 },
  visible: (delay = 0) => ({
    pathLength: 1,
    opacity: 1,
    transition: { duration: 1.4, delay, ease: [0.42, 0, 0.58, 1] },
  }),
};

export function ParcelFeasibilityShowcase() {
  const stageRef = useRef<HTMLDivElement>(null);

  useGSAP(() => {
    if (!stageRef.current) return;
    gsap.fromTo(
      stageRef.current.querySelectorAll(".gsap-feasibility-layer"),
      { scale: 0.86, opacity: 0.18, transformOrigin: "50% 50%" },
      {
        scale: 1,
        opacity: 1,
        stagger: 0.08,
        ease: "power2.out",
        scrollTrigger: {
          trigger: stageRef.current,
          start: "top 82%",
          end: "bottom 28%",
          scrub: 0.8,
        },
      },
    );
    gsap.to(stageRef.current.querySelectorAll(".gsap-score-pulse"), {
      scale: 1.06,
      repeat: -1,
      yoyo: true,
      duration: 1.8,
      ease: "sine.inOut",
      transformOrigin: "50% 50%",
    });
  }, { scope: stageRef });

  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.94, y: 28 }}
      animate={{ opacity: 1, scale: 1, y: 0 }}
      transition={{ duration: 0.9, ease: [0.22, 1, 0.36, 1], delay: 0.2 }}
      ref={stageRef}
      className="apple-product-stage group relative mx-auto w-full max-w-5xl overflow-hidden rounded-[36px] border border-[var(--color-steel-accent)] bg-[var(--color-frost-gray)] p-[14px]"
      aria-label="Animated site feasibility product visualization"
    >
      <div className="relative overflow-hidden rounded-[28px] bg-[var(--color-pure-white)] px-5 py-6 sm:px-8 sm:py-8">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_70%_12%,rgba(0,113,227,0.12),transparent_28%),radial-gradient(circle_at_18%_78%,rgba(134,104,255,0.12),transparent_24%)]" />
        <svg className="relative z-10 h-[320px] w-full sm:h-[390px]" viewBox="0 0 980 430" fill="none" role="img" aria-labelledby="parcel-title">
          <title id="parcel-title">Parcel boundary, zoning overlay, setbacks, massing and feasibility score</title>
          <defs>
            <linearGradient id="parcel-spectrum" x1="176" y1="102" x2="724" y2="342" gradientUnits="userSpaceOnUse">
              <stop stopColor="#00a1b3" stopOpacity="0.82" />
              <stop offset="0.48" stopColor="#8668ff" stopOpacity="0.72" />
              <stop offset="1" stopColor="#ed6300" stopOpacity="0.74" />
            </linearGradient>
            <linearGradient id="massing" x1="580" y1="122" x2="748" y2="298" gradientUnits="userSpaceOnUse">
              <stop stopColor="#f3f6f6" />
              <stop offset="1" stopColor="#dedfe2" />
            </linearGradient>
            <filter id="soft-blur" x="-20%" y="-20%" width="140%" height="140%">
              <feGaussianBlur stdDeviation="14" />
            </filter>
          </defs>

          <g opacity="0.55">
            {Array.from({ length: 12 }).map((_, i) => (
              <path key={`h-${i}`} d={`M80 ${70 + i * 27}H900`} stroke="#e8e8ed" strokeWidth="1" />
            ))}
            {Array.from({ length: 16 }).map((_, i) => (
              <path key={`v-${i}`} d={`M${100 + i * 50} 50V382`} stroke="#e8e8ed" strokeWidth="1" />
            ))}
          </g>

          <motion.path
            className="gsap-feasibility-layer"
            custom={0.1}
            variants={lineDraw}
            initial="hidden"
            animate="visible"
            d="M178 123L404 82L612 134L722 286L458 356L236 309Z"
            fill="url(#parcel-spectrum)"
            fillOpacity="0.2"
            stroke="url(#parcel-spectrum)"
            strokeWidth="5"
            strokeLinejoin="round"
          />
          <motion.path
            className="gsap-feasibility-layer"
            custom={0.42}
            variants={lineDraw}
            initial="hidden"
            animate="visible"
            d="M235 152L405 122L575 163L653 272L456 321L278 286Z"
            stroke="#0066cc"
            strokeWidth="3"
            strokeDasharray="10 12"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
          <motion.path
            className="gsap-feasibility-layer"
            custom={0.64}
            variants={lineDraw}
            initial="hidden"
            animate="visible"
            d="M302 182C372 151 512 168 574 216C604 239 589 284 526 294C442 309 333 286 301 240C286 218 284 195 302 182Z"
            stroke="#00a1b3"
            strokeWidth="2"
            strokeOpacity="1"
            fill="#00a1b3"
            fillOpacity="0.14"
          />
          <motion.path
            className="gsap-feasibility-layer"
            custom={0.78}
            variants={lineDraw}
            initial="hidden"
            animate="visible"
            d="M351 204C402 184 502 195 538 230C555 247 543 268 503 276C442 288 371 269 348 240C337 226 338 210 351 204Z"
            stroke="#8668ff"
            strokeWidth="2"
            strokeOpacity="1"
            fill="#8668ff"
            fillOpacity="0.14"
          />

          <motion.g
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.95, ease: [0.22, 1, 0.36, 1] }}
          >
            <path d="M598 218L681 197L738 226L654 249Z" fill="#ffffff" stroke="#cccfcf" strokeWidth="2" />
            <path d="M598 218V151L681 130V197Z" fill="url(#massing)" stroke="#cccfcf" strokeWidth="2" />
            <path d="M681 130L738 159V226L681 197Z" fill="#e8e8ed" stroke="#cccfcf" strokeWidth="2" />
            <path d="M617 165L662 154M617 187L662 176M696 160L724 174M696 184L724 198" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" opacity="0.9" />
          </motion.g>

          <motion.g
            className="gsap-score-pulse origin-center"
            initial={{ opacity: 0, scale: 0.82 }}
            animate={{ opacity: 1, scale: 1 }}
            transition={{ duration: 0.8, delay: 1.15, ease: [0.22, 1, 0.36, 1] }}
          >
            <circle cx="802" cy="119" r="58" fill="#ffffff" stroke="#cccfcf" strokeWidth="2.5" />
            <motion.circle
              cx="802"
              cy="119"
              r="42"
              fill="none"
              stroke="#0071e3"
              strokeWidth="11"
              strokeLinecap="round"
              pathLength="0.84"
              strokeDasharray="1"
              initial={{ rotate: -120 }}
              animate={{ rotate: 240 }}
              transition={{ duration: 10, repeat: Infinity, ease: "linear" }}
              style={{ transformOrigin: "802px 119px" }}
            />
            <text x="802" y="114" textAnchor="middle" className="fill-[var(--color-midnight-graphite)] text-[24px] font-semibold tracking-[-0.6px]">84</text>
            <text x="802" y="137" textAnchor="middle" className="fill-[var(--color-cloud-mist)] text-[11px] tracking-[-0.1px]">feasible</text>
          </motion.g>

          <motion.g
            initial={{ opacity: 0, x: -14 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.7, delay: 1.25 }}
          >
            <rect x="104" y="328" width="226" height="54" rx="27" fill="#ffffff" stroke="#e8e8ed" />
            <circle cx="134" cy="355" r="8" fill="#00a1b3" />
            <text x="154" y="351" className="fill-[var(--color-midnight-graphite)] text-[13px] font-semibold tracking-[-0.16px]">Zoning layer matched</text>
            <text x="154" y="369" className="fill-[var(--color-cloud-mist)] text-[11px] tracking-[-0.12px]">RM-18 density envelope</text>
          </motion.g>
          <motion.g
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 1.35 }}
          >
            <rect x="704" y="270" width="168" height="64" rx="28" fill="#1d1d1f" />
            <text x="730" y="296" className="fill-white text-[13px] font-semibold tracking-[-0.16px]">Max yield</text>
            <text x="730" y="318" className="fill-white text-[20px] font-semibold tracking-[-0.4px]">42 units</text>
            <circle cx="842" cy="302" r="12" fill="#00a1b3" />
          </motion.g>

          <motion.g
            initial={{ opacity: 0, y: -12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.7, delay: 1.45 }}
          >
            <rect x="116" y="76" width="184" height="52" rx="26" fill="#ffffff" stroke="#cccfcf" />
            <text x="143" y="100" className="fill-[var(--color-midnight-graphite)] text-[13px] font-semibold tracking-[-0.16px]">Setbacks clear</text>
            <text x="143" y="116" className="fill-[var(--color-cloud-mist)] text-[10px] tracking-[-0.12px]">18,240 sqft envelope</text>
          </motion.g>

        </svg>
      </div>
    </motion.div>
  );
}

export function MiniParcelCard({ tone = "blue" }: { tone?: "blue" | "teal" | "violet" | "orange" }) {
  const color = tone === "teal" ? "#00a1b3" : tone === "violet" ? "#8668ff" : tone === "orange" ? "#ed6300" : "#0071e3";

  return (
    <svg className="h-28 w-full" viewBox="0 0 260 112" fill="none" aria-hidden="true">
      <path d="M18 26L96 12L176 31L229 82L131 101L45 78Z" fill={color} fillOpacity="0.09" stroke={color} strokeWidth="3" strokeLinejoin="round" />
      <path d="M51 39L99 30L156 43L194 78L130 90L67 72Z" stroke="#0066cc" strokeWidth="1.5" strokeDasharray="6 7" strokeLinecap="round" />
      <path d="M91 54C116 42 155 52 166 68C173 80 150 88 122 83C97 79 77 65 91 54Z" fill={color} fillOpacity="0.12" stroke={color} strokeWidth="1.5" />
      <path d="M176 57L207 49L225 59L194 68Z" fill="#fff" stroke="#cccfcf" />
      <path d="M176 57V35L207 27V49Z" fill="#f3f6f6" stroke="#cccfcf" />
      <path d="M207 27L225 38V59L207 49Z" fill="#e8e8ed" stroke="#cccfcf" />
    </svg>
  );
}
