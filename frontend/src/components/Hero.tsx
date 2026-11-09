import { ArrowRight, Sparkles, ChevronRight } from "lucide-react";
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
        {/* Announcement badge */}
        <a
          href="#features"
          className="inline-flex items-center gap-2 bg-[#5A2F59]/8 border border-[#5A2F59]/20 hover:border-[#5A2F59]/40 px-4 py-1.5 rounded-full text-xs font-medium text-[#5A2F59] hover:text-[#4A2549] transition-all duration-300 mb-4 group cursor-pointer"
        >
          <div className="w-1.5 h-1.5 bg-[#5A2F59] rounded-full animate-pulse" />
          <span>Introducing AI-Powered Data Cleaning Suite</span>
          <ChevronRight size={12} className="text-[#BDA37A] group-hover:translate-x-0.5 transition-all" />
        </a>

        {/* Main heading */}
        <h1 className="text-4xl sm:text-5xl md:text-6xl font-extrabold tracking-tight text-center leading-[1.15] md:leading-[1.18] mb-6">
          <span className="block text-[#34434C]">
            Natural Language
          </span>
          <span className="block mt-1 sm:mt-2 text-[#34434C]">
            Meets{" "}
            <span className="text-[#70A9AA] bg-gradient-to-r from-[#70A9AA] via-[#5EA2A4] to-[#4D8C8E] bg-clip-text text-transparent">
              SQL Intelligence
            </span>
          </span>
          {/* Short, thin teal underline below the second line */}
          <span className="block w-20 sm:w-28 h-0.5 sm:h-1 bg-[#70A9AA] rounded-full mx-auto mt-4" />
        </h1>

        {/* Subtitle */}
        <p className="text-base md:text-lg text-[#566573] max-w-2xl mx-auto leading-relaxed mb-8 font-normal">
          Upload any dataset and interrogate it with plain English. PromptSQL maps your schema and generates optimized SQL — no query writing needed.
        </p>

        {/* CTA button */}
        <div className="flex flex-col sm:flex-row gap-3 justify-center items-center mb-6">
          <button
            onClick={() => {
              if (onStartQuery) {
                onStartQuery();
              } else {
                navigate("/upload");
              }
            }}
            className="group relative w-full sm:w-auto bg-[#34495E] hover:bg-[#2C3E50] border border-[#5DADE2]/30 hover:border-[#5DADE2]/60 text-white font-semibold px-7 py-3.5 rounded-xl text-sm transition-all duration-200 flex items-center justify-center gap-2.5 cursor-pointer shadow-lg shadow-[#34495E]/15"
          >
            <Sparkles size={15} className="text-[#5DADE2]" />
            <span>Start Querying </span>
            <ArrowRight size={15} className="group-hover:translate-x-0.5 transition-transform" />
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