import { useState, useEffect } from "react";
import { Sparkles, ArrowRight, Play } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useMagnetic } from "../hooks/useMagnetic";
import WorkflowMarquee from "./WorkflowMarquee";

function Typewriter({ text, delay = 0, speed = 60 }: { text: string; delay?: number; speed?: number }) {
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

export default function Hero() {
  const navigate = useNavigate();

  const handleUploadClick = () => {
    navigate("/upload");
  };

  const startQueryBtnRef = useMagnetic(0.25);
  const exploreFeaturesBtnRef = useMagnetic(0.2);

  return (
    <section className="relative pt-24 pb-12 md:pt-28 md:pb-14 bg-warmgray-50 overflow-hidden">
      {/* Decorative Warm Blur Blobs */}
      <div className="absolute top-1/4 left-1/10 w-96 h-96 bg-terracotta-300 rounded-full filter blur-3xl opacity-15 animate-pulse" />
      <div className="absolute top-1/3 right-1/10 w-96 h-96 bg-sand-200 rounded-full filter blur-3xl opacity-20 animate-pulse duration-5000" />

      <div className="relative z-10 max-w-5xl mx-auto px-6 text-center">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 bg-terracotta-50 border border-terracotta-100 px-4 py-1.5 rounded-full text-terracotta-700 font-semibold text-[10px] animate-fade-in hover:scale-103 transition-transform duration-300">
          <Sparkles size={12} className="text-terracotta-500 animate-spin-slow" />
          <span>AI-Powered Text-to-SQL Analytics Engine</span>
        </div>

        {/* Heading with Typewriter Typing animation */}
        <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl font-black text-warmgray-900 tracking-tight leading-none min-h-[110px] md:min-h-[140px]">
          <Typewriter text="Natural Language Meets" speed={50} />
          <span className="block mt-2.5 bg-gradient-to-r from-terracotta-600 via-terracotta-500 to-sand-400 bg-clip-text text-transparent">
            <Typewriter text="SQL Intelligence." delay={1500} speed={60} />
            <span className="inline-block w-1 h-7 md:h-11 bg-terracotta-500 ml-1.5 animate-blink align-middle" />
          </span>
        </h1>

        {/* Subtitle */}
        <p className="mt-5 text-sm md:text-base lg:text-lg text-warmgray-500 max-w-2xl mx-auto leading-relaxed font-medium">
          No complex database query writing, no custom schema mapping—just instant insights.
        </p>

        {/* CTAs with Magnetic mouse attraction */}
        <div className="mt-8 flex flex-col sm:flex-row gap-4 justify-center items-center">
          <button
            ref={startQueryBtnRef}
            onClick={handleUploadClick}
            className="w-full sm:w-auto bg-gradient-to-r from-terracotta-500 via-terracotta-600 to-sand-400 px-8 py-3.5 rounded-xl text-white font-bold text-sm shadow-md shadow-terracotta-500/10 hover:shadow-lg hover:shadow-terracotta-500/20 transition duration-300 flex items-center justify-center gap-2.5 cursor-pointer"
          >
            <span>Start Querying</span>
            <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
          </button>

          <a
            ref={exploreFeaturesBtnRef}
            href="#features"
            className="w-full sm:w-auto bg-white border border-warmgray-100 text-warmgray-850 px-6 py-3.5 rounded-xl font-bold text-sm hover:bg-warmgray-100 hover:text-warmgray-900 active:scale-98 transition flex items-center justify-center gap-2 cursor-pointer"
          >
            <Play size={14} className="fill-warmgray-500 text-warmgray-500" />
            <span>Explore Features</span>
          </a>
        </div>
      </div>

      {/* Loop horizontal workflow animation breakout edge-to-edge */}
      <div className="mt-14 w-full">
        <WorkflowMarquee />
      </div>
    </section>
  );
}