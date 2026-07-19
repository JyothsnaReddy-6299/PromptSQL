import { ArrowRight, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";
import ScrollFloat from "./ScrollFloat";

export default function CTA() {
  const navigate = useNavigate();

  return (
    <section className="py-28 bg-[#F7F2EC] relative overflow-hidden">
      <div className="max-w-6xl mx-auto px-6">
        <ScrollFloat>
          <div className="relative bg-[#34182F] rounded-3xl border border-[#5A2F59]/40 p-16 text-center overflow-hidden">
            {/* Glow effects */}
            <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[600px] h-[300px] bg-[#5A2F59]/30 rounded-full blur-[80px] pointer-events-none" />
            <div className="absolute bottom-0 right-1/4 w-[300px] h-[300px] bg-[#BDA37A]/15 rounded-full blur-[60px] pointer-events-none" />

            {/* Grid */}
            <div
              className="absolute inset-0 opacity-[0.04] pointer-events-none rounded-3xl"
              style={{
                backgroundImage: `linear-gradient(rgba(189,163,122,0.3) 1px, transparent 1px), linear-gradient(90deg, rgba(189,163,122,0.3) 1px, transparent 1px)`,
                backgroundSize: "60px 60px",
              }}
            />

            <div className="relative z-10 max-w-2xl mx-auto">
              <div className="inline-flex items-center gap-2 bg-[#BDA37A]/15 border border-[#BDA37A]/30 px-4 py-1.5 rounded-full text-[#BDA37A] text-xs font-medium mb-6">
                <Sparkles size={11} />
                <span>Ready in less than a minute</span>
              </div>

              <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-[#FFFDFC] mb-5 leading-tight">
                Start querying your data{" "}
                <span className="text-[#BDA37A]">today</span>
              </h2>

              <p className="text-[#E8DED3]/80 text-lg leading-relaxed mb-10">
                Upload your first dataset and get instant SQL-powered insights and AI summaries — completely free to start.
              </p>

              <div className="flex flex-col sm:flex-row gap-3 justify-center">
                <button
                  onClick={() => navigate("/upload")}
                  className="group bg-[#BDA37A] hover:bg-[#A8906A] text-[#34182F] font-semibold px-8 py-3.5 rounded-xl text-sm transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer shadow-xl shadow-[#BDA37A]/20"
                >
                  <span>Upload Your Dataset</span>
                  <ArrowRight size={15} className="group-hover:translate-x-0.5 transition-transform" />
                </button>
                <a
                  href="#features"
                  className="bg-[#5A2F59]/40 hover:bg-[#5A2F59]/60 border border-[#5A2F59]/50 hover:border-[#5A2F59]/80 text-[#FFFDFC] font-medium px-8 py-3.5 rounded-xl text-sm transition-all duration-200 flex items-center justify-center cursor-pointer"
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