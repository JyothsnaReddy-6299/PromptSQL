import { Sparkles } from "lucide-react";

export default function CTA() {
  return (
    <section className="bg-gradient-to-b from-warmgray-100 to-warmgray-50 py-20">
      <div className="max-w-5xl mx-auto px-6">
        <div className="relative bg-gradient-to-r from-terracotta-600 via-terracotta-700 to-terracotta-500 rounded-[30px] py-16 px-8 text-center overflow-hidden shadow-xl shadow-terracotta-500/10">
          {/* Decorative shapes inside container */}
          <div className="absolute top-0 right-0 w-80 h-80 bg-sand-200 rounded-full filter blur-3xl opacity-20 -translate-y-1/2 translate-x-1/3" />
          <div className="absolute bottom-0 left-0 w-80 h-80 bg-terracotta-400 rounded-full filter blur-3xl opacity-20 translate-y-1/2 -translate-x-1/3" />

          <div className="relative z-10 max-w-2xl mx-auto">
            <div className="inline-flex items-center gap-2 bg-white/10 border border-white/20 px-3.5 py-1 rounded-full text-white text-[10px] font-semibold mb-4">
              <Sparkles size={10} />
              <span>Ready in less than a minute</span>
            </div>

            <h2 className="text-3xl md:text-4xl font-extrabold text-white tracking-tight leading-none">
              Start querying your data today
            </h2>

            <p className="mt-4 text-xs md:text-sm text-terracotta-50 leading-relaxed font-medium">
              Join teams of analysts using natural language to interrogate databases, build charts, and generate detailed reports instantly.
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}