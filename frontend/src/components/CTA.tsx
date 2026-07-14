import { ArrowRight, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import ScrollFloat from "./ScrollFloat";

export default function CTA() {
  const navigate = useNavigate();

  return (
    <section className="py-28 bg-[#09090B] relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-6">
        <ScrollFloat>
          <div className="relative bg-gradient-to-br from-indigo-950/80 via-[#0D0D1A] to-violet-950/60 rounded-3xl border border-indigo-500/15 p-16 text-center overflow-hidden">
            {/* Glow effects */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-indigo-500/15 rounded-full blur-[80px] pointer-events-none" />
            <div className="absolute bottom-0 right-1/4 w-[300px] h-[300px] bg-violet-500/10 rounded-full blur-[60px] pointer-events-none" />

            {/* Grid */}
            <div
              className="absolute inset-0 opacity-[0.03] pointer-events-none rounded-3xl"
              style={{
                backgroundImage: `linear-gradient(rgba(255,255,255,0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.2) 1px, transparent 1px)`,
                backgroundSize: "60px 60px",
              }}
            />

            <div className="relative z-10 max-w-2xl mx-auto">
              <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/25 px-4 py-1.5 rounded-full text-indigo-400 text-xs font-medium mb-6">
                <Sparkles size={11} />
                <span>Ready in less than a minute</span>
              </div>

              <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white mb-5 leading-tight">
                Start querying your data{" "}
                <span className="gradient-text-purple">today</span>
              </h2>

              <p className="text-zinc-400 text-lg leading-relaxed mb-10">
                Upload your first dataset and get instant SQL-powered insights, charts, and AI summaries — completely free to start.
              </p>

              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                <button
                  onClick={() => navigate("/upload")}
                  className="group bg-white hover:bg-zinc-50 text-zinc-900 font-semibold px-8 py-3.5 rounded-xl text-sm transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer shadow-xl shadow-black/30"
                >
                  <span>Upload Your Dataset</span>
                  <ArrowRight size={15} className="group-hover:translate-x-0.5 transition-transform" />
                </button>
                <a
                  href="#features"
                  className="bg-white/[0.05] hover:bg-white/[0.08] border border-white/[0.1] hover:border-white/[0.2] text-white font-medium px-8 py-3.5 rounded-xl text-sm transition-all duration-200 flex items-center justify-center cursor-pointer"
                >
                  Learn more
                </a>
              </div>
            </div>
          </div>
        </ScrollFloat>
      </div>
    </section>
  );
}