import { useState, useEffect } from "react";
import { ArrowRight, Sparkles, ChevronRight } from "lucide-react";
import { useNavigate } from "react-router-dom";
import WorkflowMarquee from "./WorkflowMarquee";

function Typewriter({ text, delay = 0, speed = 55 }: { text: string; delay?: number; speed?: number }) {
  const [displayed, setDisplayed] = useState("");

  useEffect(() => {
    let currentLength = 0;
    const timer = setTimeout(() => {
      const interval = setInterval(() => {
        if (currentLength < text.length) {
          currentLength++;
          setDisplayed(text.slice(0, currentLength));
        } else {
          clearInterval(interval);
        }
      }, speed);
      return () => clearInterval(interval);
    }, delay);
    return () => clearTimeout(timer);
  }, [text, delay, speed]);

  return <>{displayed}</>;
}

const STATS = [
  { value: "10x", label: "Faster than writing SQL" },
  { value: "99%", label: "Query accuracy" },
  { value: "< 1s", label: "Response time" },
];

export default function Hero() {
  const navigate = useNavigate();

  return (
    <section className="relative min-h-screen flex flex-col items-center justify-center overflow-hidden bg-[#09090B]">
      {/* Radial gradient glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[900px] h-[600px] bg-indigo-600/10 rounded-full blur-[120px]" />
        <div className="absolute top-1/4 right-1/4 w-[400px] h-[400px] bg-violet-600/8 rounded-full blur-[100px]" />
        <div className="absolute bottom-1/4 left-1/4 w-[350px] h-[350px] bg-indigo-500/6 rounded-full blur-[80px]" />
      </div>

      {/* Grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.025] pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
          backgroundSize: "80px 80px",
        }}
      />

      <div className="relative z-10 max-w-5xl mx-auto px-6 text-center pt-28 pb-20">
        {/* Announcement badge */}
        <a
          href="#features"
          className="inline-flex items-center gap-2 bg-white/[0.06] border border-white/[0.1] hover:border-indigo-500/40 px-4 py-1.5 rounded-full text-xs font-medium text-zinc-300 hover:text-white transition-all duration-300 mb-8 group cursor-pointer"
        >
          <div className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-pulse" />
          <span>Introducing AI-Powered Data Cleaning Suite</span>
          <ChevronRight size={12} className="text-zinc-500 group-hover:text-indigo-400 group-hover:translate-x-0.5 transition-all" />
        </a>

        {/* Main heading */}
        <h1 className="text-5xl md:text-7xl font-bold tracking-tight text-white leading-[1.05] mb-6">
          <span className="block gradient-text">
            <Typewriter text="Natural Language" speed={50} />
          </span>
          <span className="block mt-2">
            <span className="gradient-text-purple">
              <Typewriter text="Meets SQL Intelligence" delay={1200} speed={50} />
            </span>
            <span className="inline-block w-0.5 h-12 md:h-16 bg-indigo-400 ml-2 animate-blink align-middle opacity-80" />
          </span>
        </h1>

        {/* Subtitle */}
        <p className="text-lg md:text-xl text-zinc-400 max-w-2xl mx-auto leading-relaxed mb-10 font-normal">
          Upload any dataset and interrogate it with plain English. PromptSQL maps your schema and generates optimized SQL — no query writing needed.
        </p>

        {/* CTA buttons */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center items-center mb-16">
          <button
            onClick={() => navigate("/upload")}
            className="group relative w-full sm:w-auto bg-white hover:bg-zinc-50 text-zinc-900 font-semibold px-7 py-3.5 rounded-xl text-sm transition-all duration-200 flex items-center justify-center gap-2.5 cursor-pointer shadow-lg shadow-black/20"
          >
            <Sparkles size={15} className="text-indigo-600" />
            <span>Start Querying </span>
            <ArrowRight size={15} className="group-hover:translate-x-0.5 transition-transform" />
          </button>
        </div>

        {/* Stats row */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-8 sm:gap-12 mb-16">
          {STATS.map((stat, i) => (
            <div key={i} className="text-center">
              <div className="text-2xl font-bold text-white">{stat.value}</div>
              <div className="text-xs text-zinc-500 mt-0.5">{stat.label}</div>
            </div>
          ))}
        </div>

        {/* Workflow Marquee */}
        <div className="w-full max-w-5xl mx-auto border border-white/[0.06] rounded-3xl overflow-hidden bg-black/20 shadow-inner mt-4">
          <WorkflowMarquee />
        </div>
      </div>

      {/* Bottom gradient fade into next section */}
      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-[#09090B] to-transparent pointer-events-none" />
    </section>
  );
}