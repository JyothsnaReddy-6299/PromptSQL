import { useState, useEffect } from "react";
import { ArrowRight, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import WorkflowMarquee from "./WorkflowMarquee";

const STATS = [
  { value: "10x", label: "Faster than writing SQL" },
  { value: "99%", label: "Query accuracy" },
  { value: "< 5s", label: "Response time" },
];

interface HeroProps {
  onStartQuery?: () => void;
}

export default function Hero({ onStartQuery }: HeroProps) {
  const navigate = useNavigate();

  // Typewriter effect state for "Natural Language Meets SQL Intelligence"
  const fullTextLine1 = "Natural Language";
  const fullTextLine2 = "Meets SQL Intelligence";
  const [displayText1, setDisplayText1] = useState("");
  const [displayText2, setDisplayText2] = useState("");
  const [typingPhase, setTypingPhase] = useState<"line1" | "line2" | "done">("line1");

  useEffect(() => {
    const prefersReducedMotion =
      typeof window !== "undefined" &&
      window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    if (prefersReducedMotion) {
      setDisplayText1(fullTextLine1);
      setDisplayText2(fullTextLine2);
      setTypingPhase("done");
      return;
    }

    let timer: ReturnType<typeof setTimeout>;

    if (typingPhase === "line1") {
      if (displayText1.length < fullTextLine1.length) {
        timer = setTimeout(() => {
          setDisplayText1(fullTextLine1.slice(0, displayText1.length + 1));
        }, 42);
      } else {
        timer = setTimeout(() => {
          setTypingPhase("line2");
        }, 160);
      }
    } else if (typingPhase === "line2") {
      if (displayText2.length < fullTextLine2.length) {
        timer = setTimeout(() => {
          setDisplayText2(fullTextLine2.slice(0, displayText2.length + 1));
        }, 42);
      } else {
        timer = setTimeout(() => {
          setTypingPhase("done");
        }, 450);
      }
    }
    // Only runs on initial page load / reload, does not repeatedly loop

    return () => clearTimeout(timer);
  }, [displayText1, displayText2, typingPhase]);

  // Split line 2 into "Meets " and "SQL Intelligence" for styling
  const meetsPrefix = displayText2.slice(0, 6); // "Meets "
  const sqlSuffix = displayText2.slice(6); // "SQL Intelligence"

  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center overflow-visible py-12 bg-[#F7F2EC]">
      {/* Soft radial glows matching new palette */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[600px] bg-[#34495E]/6 rounded-full blur-[120px]" />
        <div className="absolute top-1/4 right-1/4 w-[400px] h-[400px] bg-[#5DADE2]/8 rounded-full blur-[100px]" />
        <div className="absolute bottom-1/4 left-1/4 w-[350px] h-[350px] bg-[#34495E]/5 rounded-full blur-[80px]" />
      </div>

      {/* Subtle warm grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.04] pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(rgba(52,73,94,0.15) 1px, transparent 1px), linear-gradient(90deg, rgba(52,73,94,0.15) 1px, transparent 1px)`,
          backgroundSize: "80px 80px",
        }}
      />

      <div className="relative z-10 max-w-5xl mx-auto px-6 text-center pt-10 pb-6">
        {/* Main heading with Typewriter Design (scaled to balanced, comfortable font size) */}
        <h1 className="text-3xl sm:text-4xl md:text-[46px] font-extrabold tracking-tight text-center leading-[1.18] md:leading-[1.2] mb-5 min-h-[105px] sm:min-h-[120px] md:min-h-[140px] flex flex-col justify-center">
          <span className="block text-[#34434C]">
            {displayText1}
            {typingPhase === "line1" && (
              <span className="inline-block w-1 sm:w-1.5 h-[0.82em] bg-[#70A9AA] ml-1.5 animate-pulse align-middle" />
            )}
          </span>
          <span className="block mt-1 sm:mt-1.5 text-[#34434C]">
            {meetsPrefix}
            {sqlSuffix && (
              <span className="text-[#70A9AA] bg-gradient-to-r from-[#70A9AA] via-[#5EA2A4] to-[#4D8C8E] bg-clip-text text-transparent">
                {sqlSuffix}
              </span>
            )}
            {(typingPhase === "line2" || typingPhase === "done") && (
              <span className="inline-block w-1 sm:w-1.5 h-[0.82em] bg-[#70A9AA] ml-1.5 animate-pulse align-middle" />
            )}
          </span>
          {/* Short, thin teal underline below the second line */}
          <span
            className={`block w-16 sm:w-24 h-0.5 sm:h-1 bg-[#70A9AA] rounded-full mx-auto mt-3.5 transition-opacity duration-700 ${
              typingPhase === "done" ? "opacity-100" : "opacity-0"
            }`}
          />
        </h1>

        {/* Subtitle */}
        <p className="text-sm sm:text-base text-[#566573] max-w-xl mx-auto leading-relaxed mb-7 font-normal">
          Upload any dataset and interrogate it with plain English. PromptSQL maps your schema and generates optimized SQL — no query writing needed.
        </p>

        {/* CTA button with Video 2 Liquid Wave Wipe Style */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center items-center mb-6">
          <button
            onClick={() => {
              if (onStartQuery) {
                onStartQuery();
              } else {
                navigate("/upload");
              }
            }}
            className="group relative overflow-hidden w-full sm:w-auto bg-[#70A9AA] border border-[#5EA2A4] text-white font-semibold px-8 py-3.5 rounded-2xl text-sm transition-all duration-300 flex items-center justify-center gap-2.5 cursor-pointer shadow-lg shadow-[#70A9AA]/25 hover:shadow-xl hover:shadow-black/10 active:scale-95"
          >
            {/* Liquid curved wave wipe */}
            <span className="absolute -top-[50%] -left-[10%] w-[120%] h-[200%] bg-[#FFFDFC] rounded-b-[50%] -translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out pointer-events-none" />
            <span className="relative z-10 flex items-center gap-2.5 transition-colors duration-300 group-hover:text-[#241C20]">
              <Sparkles size={16} className="text-[#E1F0EF] group-hover:text-[#70A9AA] transition-colors" />
              <span>Start Querying</span>
              <ArrowRight size={15} className="group-hover:translate-x-1 transition-transform" />
            </span>
          </button>
        </div>

        {/* Stats row */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-8 sm:gap-12 mb-4">
          {STATS.map((stat, i) => (
            <div key={i} className="text-center">
              <div className="text-2xl font-bold text-[#34495E]">{stat.value}</div>
              <div className="text-xs text-[#566573] mt-0.5">{stat.label}</div>
            </div>
          ))}
        </div>
      </div>

      {/* Workflow Marquee (Placed outside the max-w-5xl text wrapper to span from screen edge to screen edge) */}
      <div className="w-full relative z-10 mt-4 overflow-hidden">
        <WorkflowMarquee />
      </div>

      {/* Bottom gradient fade */}
      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-[#F4F6F7] to-transparent pointer-events-none" />
    </section>
  );
}