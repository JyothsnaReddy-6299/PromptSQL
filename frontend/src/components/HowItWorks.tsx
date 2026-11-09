import { useState, useEffect, useRef, useCallback } from "react";
import {
  UploadCloud,
  Database,
  MessageSquareQuote,
  FileCode2,
  TableProperties,
  Sparkles,
} from "lucide-react";

interface ProcessStep {
  step: string;
  number: string;
  title: string;
  desc: string;
  icon: typeof UploadCloud;
  accent: {
    bg: string;
    border: string;
    text: string;
    nodeGlow: string;
  };
}

const STEPS: ProcessStep[] = [
  {
    step: "01",
    number: "01",
    title: "Upload Your Dataset",
    desc: "Import your Excel or CSV file and get your data ready for analysis.",
    icon: UploadCloud,
    accent: {
      bg: "bg-[#E1F0EF]",
      border: "border-[#C2E4E2]",
      text: "text-[#70A9AA]",
      nodeGlow: "bg-[#70A9AA]",
    },
  },
  {
    step: "02",
    number: "02",
    title: "Let AI Understand Your Data",
    desc: "PromptSQL identifies your tables, columns, data types and relationships.",
    icon: Database,
    accent: {
      bg: "bg-[#E8EFFB]",
      border: "border-[#CADBFA]",
      text: "text-[#4A7FD4]",
      nodeGlow: "bg-[#4A7FD4]",
    },
  },
  {
    step: "03",
    number: "03",
    title: "Ask in Plain English",
    desc: "Simply type the question you want answered. No SQL knowledge required.",
    icon: MessageSquareQuote,
    accent: {
      bg: "bg-[#FCE9E3]",
      border: "border-[#F7CDBC]",
      text: "text-[#DE6846]",
      nodeGlow: "bg-[#DE6846]",
    },
  },
  {
    step: "04",
    number: "04",
    title: "Generate and Validate SQL",
    desc: "AI translates your question into SQL and validates the generated query before execution.",
    icon: FileCode2,
    accent: {
      bg: "bg-[#F0EAF9]",
      border: "border-[#DCCEF2]",
      text: "text-[#7D52B8]",
      nodeGlow: "bg-[#7D52B8]",
    },
  },
  {
    step: "05",
    number: "05",
    title: "Get Your Results",
    desc: "Execute the query and explore your results in a clear, understandable format.",
    icon: TableProperties,
    accent: {
      bg: "bg-[#E8F5E9]",
      border: "border-[#C8E6C9]",
      text: "text-[#2E7D32]",
      nodeGlow: "bg-[#2E7D32]",
    },
  },
];

// Moving Snake animation parameters
const SNAKE_LENGTH = 160; // Length of the luminous snake body (px)
const SNAKE_CYCLE_DURATION = 9500; // 9.5s per continuous wave cycle for slow, graceful slither

export default function HowItWorks() {
  const sectionRef = useRef<HTMLElement>(null);
  const timelineContainerRef = useRef<HTMLDivElement>(null);
  const cardsContainerRef = useRef<HTMLDivElement>(null);
  const cardRefs = useRef<(HTMLDivElement | null)[]>([]);
  const pathRef = useRef<SVGPathElement>(null);

  const [isInView, setIsInView] = useState(false);
  const [activeStep, setActiveStep] = useState(0);
  const [hoveredStep, setHoveredStep] = useState<number | null>(null);

  const [pathData, setPathData] = useState<string>("");
  const [pathLength, setPathLength] = useState<number>(0);
  const [markerPoints, setMarkerPoints] = useState<{ x: number; y: number }[]>([]);
  const [snakeOffset, setSnakeOffset] = useState<number>(0);
  const [snakeHead, setSnakeHead] = useState<{ x: number; y: number } | null>(null);
  const [snakeOpacity, setSnakeOpacity] = useState<number>(1);
  const markerDistancesRef = useRef<number[]>([0, 0, 0, 0, 0]);

  const pauseStartRef = useRef<number | null>(null);
  const totalPausedTimeRef = useRef<number>(0);
  const animStartTimeRef = useRef<number | null>(null);

  // 1. Trigger reveal when section enters view
  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => {
        setIsInView(entry.isIntersecting);
      },
      { threshold: 0.15 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // 2. Measure card center positions and construct bold alternating wave SVG path
  const recalculateCurve = useCallback(() => {
    const container = timelineContainerRef.current;
    if (!container) return;
    const containerRect = container.getBoundingClientRect();

    const xs: number[] = [];
    for (let i = 0; i < STEPS.length; i++) {
      const cardEl = cardRefs.current[i];
      if (!cardEl) return;
      const cardRect = cardEl.getBoundingClientRect();
      xs.push(cardRect.left + cardRect.width / 2 - containerRect.left);
    }

    if (xs.length < 5) return;

    // Pronounced alternating wave heights (scaled to tight, balanced timeline):
    // Step 01: Valley (115px) - 01 placed ABOVE
    // Step 02: Peak (20px)   - 02 placed BELOW
    // Step 03: Valley (115px) - 03 placed ABOVE
    // Step 04: Peak (20px)   - 04 placed BELOW
    // Step 05: Valley (115px) - 05 placed ABOVE
    const yPeak = 20;
    const yValley = 115;
    const ys = [yValley, yPeak, yValley, yPeak, yValley];

    const points = xs.map((x, i) => ({ x, y: ys[i] }));
    setMarkerPoints(points);

    // Build continuous cubic Bézier S-curve wave with horizontal tangents at every marker
    let d = `M ${points[0].x.toFixed(2)} ${points[0].y.toFixed(2)}`;
    for (let i = 0; i < points.length - 1; i++) {
      const pStart = points[i];
      const pEnd = points[i + 1];
      const dx = pEnd.x - pStart.x;

      const cp1x = pStart.x + dx * 0.5;
      const cp1y = pStart.y;
      const cp2x = pEnd.x - dx * 0.5;
      const cp2y = pEnd.y;

      d += ` C ${cp1x.toFixed(2)} ${cp1y.toFixed(2)}, ${cp2x.toFixed(2)} ${cp2y.toFixed(2)}, ${pEnd.x.toFixed(2)} ${pEnd.y.toFixed(2)}`;
    }

    setPathData(d);
  }, []);

  // Recalculate on mount, resize observer, and window resize
  useEffect(() => {
    recalculateCurve();
    const handleResize = () => recalculateCurve();
    window.addEventListener("resize", handleResize);

    const cardsEl = cardsContainerRef.current;
    let resizeObserver: ResizeObserver | null = null;
    if (cardsEl && typeof ResizeObserver !== "undefined") {
      resizeObserver = new ResizeObserver(() => recalculateCurve());
      resizeObserver.observe(cardsEl);
    }

    const timer = setTimeout(recalculateCurve, 120);

    return () => {
      window.removeEventListener("resize", handleResize);
      if (resizeObserver) resizeObserver.disconnect();
      clearTimeout(timer);
    };
  }, [recalculateCurve]);

  // 3. Measure exact distances along the wave path for the 5 step stops
  useEffect(() => {
    const path = pathRef.current;
    if (!path || !pathData || markerPoints.length < 5) return;
    const totalLength = path.getTotalLength();
    if (totalLength <= 0) return;

    setPathLength(totalLength);

    const stops: number[] = [0];
    for (let i = 1; i < STEPS.length - 1; i++) {
      const targetX = markerPoints[i].x;

      // Binary search along the path for the distance where X matches marker center
      let low = 0;
      let high = totalLength;
      for (let iter = 0; iter < 24; iter++) {
        const mid = (low + high) / 2;
        const pt = path.getPointAtLength(mid);
        if (pt.x < targetX) {
          low = mid;
        } else {
          high = mid;
        }
      }
      stops.push((low + high) / 2);
    }
    stops.push(totalLength);
    markerDistancesRef.current = stops;
  }, [pathData, markerPoints]);

  // 4. Slow Moving Snake continuous slithering animation loop
  useEffect(() => {
    if (!isInView || !pathData || pathLength <= 0) return;
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReducedMotion) {
      setActiveStep(0);
      const path = pathRef.current;
      if (path && path.getTotalLength() > 0) {
        const pt = path.getPointAtLength(0);
        setSnakeHead({ x: pt.x, y: pt.y });
        setSnakeOffset(0);
      }
      return;
    }

    let rafId: number;

    const tick = (now: number) => {
      // Pause snake movement while user hovers a card so they can inspect comfortably
      if (hoveredStep !== null) {
        if (pauseStartRef.current === null) {
          pauseStartRef.current = now;
        }
        rafId = requestAnimationFrame(tick);
        return;
      }

      if (pauseStartRef.current !== null) {
        totalPausedTimeRef.current += now - pauseStartRef.current;
        pauseStartRef.current = null;
      }

      if (animStartTimeRef.current === null) {
        animStartTimeRef.current = now;
      }

      const elapsed = Math.max(
        0,
        now - animStartTimeRef.current - totalPausedTimeRef.current
      );

      // Continuous loop: snake travels total distance = pathLength + SNAKE_LENGTH
      const totalTravel = pathLength + SNAKE_LENGTH;
      const progress = (elapsed % SNAKE_CYCLE_DURATION) / SNAKE_CYCLE_DURATION;
      const currentHeadDist = progress * totalTravel;

      // Dash offset to position snake body along the curve
      const offset = SNAKE_LENGTH - currentHeadDist;
      setSnakeOffset(offset);

      const path = pathRef.current;
      if (path && pathLength > 0) {
        const clampedDist = Math.min(pathLength, Math.max(0, currentHeadDist));
        const pt = path.getPointAtLength(clampedDist);
        setSnakeHead({ x: pt.x, y: pt.y });

        // Smooth fade-in at start and fade-out at end of wave
        if (currentHeadDist > pathLength) {
          const fade = 1 - (currentHeadDist - pathLength) / SNAKE_LENGTH;
          setSnakeOpacity(Math.max(0, fade));
        } else if (currentHeadDist < SNAKE_LENGTH * 0.4) {
          setSnakeOpacity(Math.min(1, currentHeadDist / (SNAKE_LENGTH * 0.4)));
        } else {
          setSnakeOpacity(1);
        }

        // Determine which step is currently active as the snake slithers past
        const stops = markerDistancesRef.current;
        if (stops.length === STEPS.length) {
          let closestIdx = 0;
          let minDiff = Infinity;
          for (let i = 0; i < stops.length; i++) {
            const diff = Math.abs(clampedDist - stops[i]);
            if (diff < minDiff) {
              minDiff = diff;
              closestIdx = i;
            }
          }
          setActiveStep(closestIdx);
        }
      }

      rafId = requestAnimationFrame(tick);
    };

    rafId = requestAnimationFrame(tick);

    return () => {
      cancelAnimationFrame(rafId);
    };
  }, [isInView, pathData, pathLength, hoveredStep]);

  // Current active step responds to mouse hover or automated snake playback
  const currentActive = hoveredStep !== null ? hoveredStep : activeStep;

  return (
    <section
      id="how-it-works"
      ref={sectionRef}
      className="py-16 sm:py-20 bg-[#F0F3F3] relative overflow-hidden text-[#34434C] border-t border-[#DFE7EA]"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 relative z-10">
        {/* Section Heading & Eyebrow */}
        <div className="text-center max-w-2xl mx-auto mb-10 sm:mb-12">
          {/* Eyebrow Label */}
          <div className="inline-flex items-center gap-2 bg-[#E1F0EF] border border-[#C2E4E2] px-3.5 py-1 rounded-full text-[#2B5758] text-[11px] font-semibold tracking-wider uppercase mb-3.5 shadow-2xs">
            <Sparkles size={12} className="text-[#70A9AA]" />
            <span>HOW PROMPTSQL WORKS</span>
          </div>

          {/* Main Heading */}
          <h2 className="text-2xl sm:text-3xl md:text-4xl font-extrabold tracking-tight text-[#34434C] leading-[1.15] mb-3">
            Up and running in{" "}
            <span className="text-[#70A9AA] bg-gradient-to-r from-[#70A9AA] via-[#5BA0A2] to-[#458B8D] bg-clip-text text-transparent">
              seconds
            </span>
          </h2>

          {/* Supporting Text */}
          <p className="text-sm sm:text-base text-[#687985] leading-relaxed font-normal">
            Five simple steps. No SQL expertise required. Upload your dataset, ask questions and get meaningful answers.
          </p>
        </div>

        {/* ── DESKTOP & TABLET WAVE TIMELINE LAYOUT (md / lg) ── */}
        <div className="hidden md:block">
          {/* 1. Dedicated Wave Timeline Area with Alternating Step Numbers & Markers */}
          <div
            ref={timelineContainerRef}
            className="relative h-[135px] overflow-visible my-1"
          >
            {/* The Continuous SVG Wave Connector */}
            <svg
              className="absolute inset-0 w-full h-full pointer-events-none overflow-visible"
              aria-hidden="true"
            >
              {/* Base dashed guideline track */}
              {pathData && (
                <path
                  ref={pathRef}
                  d={pathData}
                  fill="none"
                  stroke="#A9C9CA"
                  strokeWidth="2"
                  strokeDasharray="5 6"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}

              {/* Slow Moving Luminous Snake Body following the curve */}
              {pathData && pathLength > 0 && (
                <g style={{ opacity: snakeOpacity, transition: "opacity 0.2s ease" }}>
                  {/* Soft outer glow of snake body */}
                  <path
                    d={pathData}
                    fill="none"
                    stroke="#70A9AA"
                    strokeWidth="6"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    opacity="0.22"
                    strokeDasharray={`${SNAKE_LENGTH} ${pathLength + SNAKE_LENGTH}`}
                    strokeDashoffset={snakeOffset}
                  />
                  {/* Core solid snake beam */}
                  <path
                    d={pathData}
                    fill="none"
                    stroke="#70A9AA"
                    strokeWidth="3"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    opacity="0.95"
                    strokeDasharray={`${SNAKE_LENGTH} ${pathLength + SNAKE_LENGTH}`}
                    strokeDashoffset={snakeOffset}
                  />
                </g>
              )}

              {/* The Snake Head Node (Leading Tip) */}
              {snakeHead && (
                <g
                  transform={`translate(${snakeHead.x}, ${snakeHead.y})`}
                  style={{ opacity: snakeOpacity, transition: "opacity 0.2s ease" }}
                >
                  <circle r="8" fill="#70A9AA" opacity="0.28" />
                  <circle
                    r="4.5"
                    fill="#70A9AA"
                    stroke="#FFFFFF"
                    strokeWidth="1.5"
                  />
                </g>
              )}
            </svg>

            {/* Step Numbers & Markers Positioned Organically Along the Wave */}
            {markerPoints.map((pt, idx) => {
              const isCurrent = currentActive === idx;
              // Alternating positioning: 01, 03, 05 are valleys (ABOVE dot); 02, 04 are peaks (BELOW dot)
              const isValley = idx % 2 === 0;

              return (
                <div
                  key={STEPS[idx].step}
                  onMouseEnter={() => setHoveredStep(idx)}
                  onMouseLeave={() => setHoveredStep(null)}
                  onClick={() => setActiveStep(idx)}
                  className="absolute cursor-pointer transition-all duration-300 z-10 group"
                  style={{
                    left: `${pt.x}px`,
                    top: `${pt.y}px`,
                  }}
                >
                  {/* Step Circular Marker (centered exactly at pt.x, pt.y on the wave path) */}
                  <div className="absolute -translate-x-1/2 -translate-y-1/2">
                    <div
                      className={`w-6 h-6 rounded-full bg-white flex items-center justify-center transition-all duration-300 shadow-xs ${
                        isCurrent
                          ? "border-2 border-[#70A9AA] scale-125 ring-4 ring-[#70A9AA]/20"
                          : "border border-[#CBD8DC] group-hover:border-[#70A9AA]"
                      }`}
                    >
                      <span
                        className={`w-2 h-2 rounded-full transition-colors duration-300 ${
                          isCurrent
                            ? "bg-[#70A9AA]"
                            : "bg-[#CBD8DC] group-hover:bg-[#70A9AA]/60"
                        }`}
                      />
                    </div>
                  </div>

                  {/* Step Number: Bold, lengthy display numerals (01 ABOVE dot, 02 BELOW dot, etc.) */}
                  <div
                    className={`absolute left-1/2 -translate-x-1/2 flex flex-col items-center select-none transition-transform duration-300 ${
                      isCurrent ? "scale-105" : "group-hover:scale-105"
                    }`}
                    style={
                      isValley
                        ? { bottom: "14px" } // Positioned above the valley marker
                        : { top: "14px" }    // Positioned below the peak marker
                    }
                  >
                    <span className="text-[11px] font-black uppercase tracking-widest text-[#70A9AA] leading-none mb-1">
                      STEP
                    </span>
                    <span
                      className={`font-['Bebas_Neue',_Impact,_sans-serif] text-5xl sm:text-[54px] lg:text-[58px] tracking-tight leading-none transition-colors duration-300 ${
                        isCurrent
                          ? "text-[#70A9AA]"
                          : "text-[#34434C] group-hover:text-[#70A9AA]"
                      }`}
                    >
                      {STEPS[idx].number}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>

          {/* 2. Clearly Separated Row of Feature Cards Below (Arranged According to the Wave Pattern) */}
          <div
            ref={cardsContainerRef}
            className="grid grid-cols-5 gap-3 lg:gap-4 items-stretch relative z-10 mt-3"
          >
            {STEPS.map((step, idx) => {
              const Icon = step.icon;
              const isCurrent = currentActive === idx;
              const isValley = idx % 2 === 0;

              // Alternating wave translation for cards:
              // Peak cards (02, 04): shifted UP towards their peaks (-translate-y-5)
              // Valley cards (01, 03, 05): sitting comfortably below their valleys (translate-y-1)
              const waveYClass = isValley
                ? isCurrent
                  ? "md:translate-y-0"
                  : "md:translate-y-1"
                : isCurrent
                ? "md:-translate-y-6"
                : "md:-translate-y-5";

              // Smooth fly-in entrance on scroll
              const flyInClass = isInView
                ? `opacity-100 ${waveYClass} scale-100`
                : "opacity-0 translate-y-12 md:translate-y-12 scale-95 pointer-events-none";

              return (
                <div
                  key={step.step}
                  ref={(el) => {
                    cardRefs.current[idx] = el;
                  }}
                  onMouseEnter={() => setHoveredStep(idx)}
                  onMouseLeave={() => setHoveredStep(null)}
                  onClick={() => setActiveStep(idx)}
                  className={`group bg-white rounded-2xl border p-4 lg:p-5 flex flex-col justify-between h-[215px] lg:h-[225px] w-full transition-all duration-700 ease-out cursor-pointer ${flyInClass} ${
                    isCurrent
                      ? "border-[#70A9AA] shadow-[0_14px_30px_rgba(112,169,170,0.18)] ring-1 ring-[#70A9AA]/30"
                      : "border-[#DFE7EA] shadow-[0_2px_12px_rgba(52,67,76,0.03)] hover:shadow-md hover:border-[#70A9AA]/60"
                  }`}
                  style={{
                    transitionDelay: isInView ? `${idx * 100 + 100}ms` : "0ms",
                  }}
                >
                  {/* Pastel Icon Box */}
                  <div
                    className={`w-11 h-11 rounded-2xl flex items-center justify-center mb-3.5 border shrink-0 transition-all duration-300 ${
                      isCurrent
                        ? "scale-105 ring-2 ring-[#70A9AA]/25 shadow-xs"
                        : "group-hover:scale-105"
                    } ${step.accent.bg} ${step.accent.border} ${step.accent.text}`}
                  >
                    <Icon size={20} />
                  </div>

                  {/* Text Container with aligned baseline */}
                  <div className="flex-1 flex flex-col justify-start">
                    {/* Step Title - uniform min-height so descriptions align */}
                    <h3
                      className={`font-bold text-sm lg:text-[15px] leading-snug transition-colors mb-2 min-h-[42px] flex items-center ${
                        isCurrent
                          ? "text-[#1F2937]"
                          : "text-[#34434C] group-hover:text-[#1F2937]"
                      }`}
                    >
                      {step.title}
                    </h3>

                    {/* Description */}
                    <p className="text-xs text-[#687985] leading-relaxed">
                      {step.desc}
                    </p>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        {/* ── MOBILE VERTICAL TIMELINE LAYOUT (< 768px) ── */}
        <div className="md:hidden relative pl-6 space-y-6">
          {/* Vertical Dashed Line along the left side */}
          <div className="absolute top-4 bottom-4 left-3 w-0.5 border-l-2 border-dashed border-[#A9C9CA] z-0" />

          {STEPS.map((step, idx) => {
            const Icon = step.icon;
            const isCurrent = currentActive === idx;

            return (
              <div
                key={step.step}
                onClick={() => setActiveStep(idx)}
                className={`relative flex items-start gap-4 transition-all duration-500 ${
                  isInView
                    ? "opacity-100 translate-x-0"
                    : "opacity-0 -translate-x-4"
                }`}
                style={{ transitionDelay: `${idx * 100}ms` }}
              >
                {/* Vertical Node Ring */}
                <div
                  className={`absolute -left-[23px] top-4 w-6 h-6 rounded-full bg-white flex items-center justify-center shadow-xs z-10 transition-all duration-300 ${
                    isCurrent
                      ? "border-2 border-[#70A9AA] scale-110 ring-4 ring-[#70A9AA]/20"
                      : "border border-[#CBD8DC]"
                  }`}
                >
                  <span
                    className={`w-2 h-2 rounded-full transition-colors duration-300 ${
                      isCurrent ? "bg-[#70A9AA]" : "bg-[#CBD8DC]"
                    }`}
                  />
                </div>

                {/* Mobile Step Card */}
                <div
                  className={`bg-white rounded-2xl border p-4.5 w-full transition-all duration-300 ${
                    isCurrent
                      ? "border-[#70A9AA] ring-1 ring-[#70A9AA]/25 shadow-md -translate-y-0.5"
                      : "border-[#DFE7EA] shadow-xs hover:border-[#70A9AA]/60"
                  }`}
                >
                  <div className="flex items-center gap-2.5 mb-2.5">
                    <div
                      className={`w-9 h-9 rounded-xl flex items-center justify-center border ${step.accent.bg} ${step.accent.border} ${step.accent.text}`}
                    >
                      <Icon size={18} />
                    </div>
                    <span
                      className={`text-sm font-['Bebas_Neue',_Impact,_sans-serif] tracking-wider transition-colors ${
                        isCurrent ? "text-[#70A9AA]" : "text-[#70A9AA]/80"
                      }`}
                    >
                      STEP {step.number}
                    </span>
                  </div>

                  <h3 className="font-bold text-[#34434C] text-sm leading-snug mb-1">
                    {step.title}
                  </h3>
                  <p className="text-xs text-[#687985] leading-relaxed">
                    {step.desc}
                  </p>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
