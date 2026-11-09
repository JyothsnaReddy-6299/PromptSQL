import { useState, useEffect, useRef } from "react";
import { Sparkles, Terminal, CheckCircle2, CornerDownLeft, Loader2 } from "lucide-react";

interface QueryScenario {
  question: string;
  sql: string[];
  result: string;
  latency: string;
}

const SCENARIOS: QueryScenario[] = [
  {
    question: "Which product generated the highest revenue?",
    sql: [
      "SELECT product_name, SUM(revenue) AS total_revenue",
      "FROM ecommerce_sales",
      "GROUP BY product_name",
      "ORDER BY total_revenue DESC LIMIT 1;",
    ],
    result: "Enterprise Suite — $184,250",
    latency: "0.28s",
  },
  {
    question: "Show total customer orders grouped by region for 2026",
    sql: [
      "SELECT region, COUNT(order_id) AS total_orders",
      "FROM customer_orders",
      "WHERE YEAR(order_date) = 2026",
      "GROUP BY region ORDER BY total_orders DESC;",
    ],
    result: "North America (4,821) · Europe (3,190)",
    latency: "0.32s",
  },
];

export default function NaturalLanguageSQLCard() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(true);
  const [scenarioIdx, setScenarioIdx] = useState(0);

  // Animation Sequence Phase: 0 = Typing, 1 = AI Processing, 2 = SQL Reveal, 3 = Executed Success
  const [phase, setPhase] = useState<0 | 1 | 2 | 3>(0);
  const [typedChars, setTypedChars] = useState(0);

  const current = SCENARIOS[scenarioIdx];

  // IntersectionObserver to pause loop when off-screen
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      ([entry]) => setIsVisible(entry.isIntersecting),
      { threshold: 0.1 }
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Main Animation Sequencer Loop
  useEffect(() => {
    if (!isVisible) return;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) {
      setPhase(3);
      setTypedChars(current.question.length);
      return;
    }

    let timer: ReturnType<typeof setTimeout>;

    if (phase === 0) {
      // Snappy typing phase
      if (typedChars < current.question.length) {
        timer = setTimeout(() => {
          // Increment in steps of 2 chars or 1 for snappy natural cadence
          setTypedChars((prev) => Math.min(prev + 2, current.question.length));
        }, 22);
      } else {
        // Typing finished -> Move to AI Processing promptly
        timer = setTimeout(() => setPhase(1), 250);
      }
    } else if (phase === 1) {
      // Fast AI Processing
      timer = setTimeout(() => setPhase(2), 450);
    } else if (phase === 2) {
      // Snappy SQL Reveal
      timer = setTimeout(() => setPhase(3), 550);
    } else if (phase === 3) {
      // Success state displayed, then reset & cycle to next scenario
      timer = setTimeout(() => {
        setTypedChars(0);
        setPhase(0);
        setScenarioIdx((prev) => (prev + 1) % SCENARIOS.length);
      }, 2400);
    }

    return () => clearTimeout(timer);
  }, [isVisible, phase, typedChars, current.question.length]);

  return (
    <div ref={containerRef} className="w-full space-y-2.5">
      {/* 1. Natural Language Input Box on Soft Mint/Teal Pastel Canvas (#E1F0EF) */}
      <div className="bg-gradient-to-br from-[#E1F0EF]/80 via-[#EDF7F6] to-[#E1F0EF]/50 rounded-xl p-3 border border-[#C2E4E2] shadow-2xs">
        <div className="flex items-center justify-between text-xs text-[#556976] mb-2">
          <div className="flex items-center gap-1.5 font-semibold text-[#2B5758]">
            <Sparkles size={13} className="text-[#70A9AA] animate-pulse" />
            <span className="uppercase tracking-wider text-[9px]">Natural Language Prompt</span>
          </div>
          <span className="text-[9px] text-[#70A9AA] font-mono bg-white/80 px-2 py-0.5 rounded-full border border-[#C2E4E2]">
            Auto-Translating
          </span>
        </div>

        {/* Typing Input */}
        <div className="flex items-center gap-2 bg-white rounded-lg px-3 py-2 border border-[#C2E4E2] shadow-2xs">
          <span className="text-[#70A9AA] font-mono font-bold select-none text-xs">&gt;</span>
          <p className="text-xs font-medium text-[#34434C] flex-1 truncate">
            {current.question.slice(0, typedChars)}
            {phase === 0 && <span className="inline-block w-1 h-3.5 bg-[#70A9AA] ml-0.5 animate-pulse" />}
          </p>
          <CornerDownLeft size={12} className="text-[#9AA8B2]" />
        </div>
      </div>

      {/* 2. Progressive SQL Generation & Execution Box */}
      <div className="bg-[#172832] text-white rounded-xl p-3 border border-[#2F4A58] shadow-md font-mono relative overflow-hidden transition-all duration-500">
        {/* Terminal Header */}
        <div className="flex items-center justify-between pb-1.5 mb-2 border-b border-[#2F4A58]/80 text-[10px]">
          <div className="flex items-center gap-1.5">
            <div className="flex gap-1">
              <span className="w-2 h-2 rounded-full bg-[#FF5F56]/80 inline-block" />
              <span className="w-2 h-2 rounded-full bg-[#FFBD2E]/80 inline-block" />
              <span className="w-2 h-2 rounded-full bg-[#27C93F]/80 inline-block" />
            </div>
            <span className="text-[#A5BAC6] flex items-center gap-1 font-semibold ml-1.5">
              <Terminal size={11} className="text-[#70A9AA]" />
              <span>compiled_query.sql</span>
            </span>
          </div>

          {/* AI Status Indicator */}
          {phase === 1 && (
            <div className="flex items-center gap-1 text-[9px] text-[#70A9AA] font-sans animate-pulse">
              <Loader2 size={10} className="animate-spin" />
              <span>AI Synthesizing SQL...</span>
            </div>
          )}
          {phase >= 2 && (
            <span className="text-[9px] text-emerald-400 font-sans font-medium flex items-center gap-1">
              <CheckCircle2 size={10} />
              <span>Verified AST</span>
            </span>
          )}
        </div>

        {/* Code Lines with Progressive Fade-in */}
        <div className="min-h-[64px] flex flex-col justify-center text-[11px] leading-relaxed text-[#DFEBF2]">
          {phase >= 2 ? (
            current.sql.map((line, i) => (
              <div
                key={i}
                className="flex items-baseline transition-all duration-300 transform translate-y-0 opacity-100"
                style={{ animationDelay: `${i * 120}ms` }}
              >
                <span className="text-[#556976] select-none w-5 text-right mr-2.5 text-[10px] font-sans">
                  {i + 1}
                </span>
                <span className="font-mono">
                  {line
                    .split(" ")
                    .map((word, wIdx) => {
                      const isKeyword = ["SELECT", "FROM", "WHERE", "GROUP", "BY", "ORDER", "DESC", "LIMIT", "AS", "COUNT", "SUM", "YEAR"].includes(word.replace(/[,;]/g, ""));
                      return (
                        <span
                          key={wIdx}
                          className={isKeyword ? "text-[#8BC5C5] font-bold" : "text-[#DFEBF2]"}
                        >
                          {word}{" "}
                        </span>
                      );
                    })}
                </span>
              </div>
            ))
          ) : (
            <div className="text-[11px] text-[#6D8796] italic flex items-center gap-2 py-3">
              <span className="w-2 h-2 rounded-full bg-[#70A9AA] animate-ping" />
              <span>Waiting for query input stream...</span>
            </div>
          )}
        </div>

        {/* Successful Query Status Pill (Phase 3) */}
        <div
          className={`mt-2.5 pt-2 border-t border-[#2F4A58]/80 flex flex-wrap items-center justify-between text-[11px] transition-all duration-500 ${
            phase === 3 ? "opacity-100 translate-y-0" : "opacity-30"
          }`}
        >
          <div className="flex items-center gap-1.5 font-sans">
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <span className="text-emerald-300 font-medium">Query Executed</span>
            <span className="text-[#6D8796]">·</span>
            <span className="text-[#DFEBF2] truncate max-w-[200px] sm:max-w-none">{current.result}</span>
          </div>
          <span className="text-[10px] text-[#8BC5C5] font-mono font-bold">{current.latency}</span>
        </div>
      </div>
    </div>
  );
}
