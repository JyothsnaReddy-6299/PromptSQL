import { useState, useEffect, useRef } from "react";
import { KeyRound, Table, Database, Check } from "lucide-react";

export default function SchemaUnderstandingCard() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(true);

  // Animation Step: 0 = Init/Scanning, 1 = Columns parsed, 2 = PK & Indexes verified
  const [step, setStep] = useState<0 | 1 | 2>(0);

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

  useEffect(() => {
    if (!isVisible) return;
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (prefersReducedMotion) {
      setStep(2);
      return;
    }

    let timer: ReturnType<typeof setTimeout>;

    if (step === 0) {
      timer = setTimeout(() => setStep(1), 320);
    } else if (step === 1) {
      timer = setTimeout(() => setStep(2), 600);
    } else if (step === 2) {
      // Hold verified state, then loop back
      timer = setTimeout(() => setStep(0), 2200);
    }

    return () => clearTimeout(timer);
  }, [isVisible, step]);

  return (
    <div
      ref={containerRef}
      className="w-full bg-gradient-to-br from-[#E8EFFB]/85 via-[#F2F6FD] to-[#E8EFFB]/50 border border-[#CADBFA] rounded-xl p-3 sm:p-3.5 relative overflow-hidden shadow-2xs"
    >
      <div className="flex items-center justify-between text-xs text-[#556976] mb-2.5">
        <span className="font-semibold text-[10px] text-[#2C5294] flex items-center gap-1.5">
          <Database size={12} className="text-[#4A7FD4]" />
          <span>Relational Schema Graph</span>
        </span>
        <span
          className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border transition-all duration-300 flex items-center gap-1 ${
            step === 2
              ? "bg-[#4A7FD4] text-white border-[#4A7FD4] shadow-xs"
              : "bg-white text-[#4A7FD4] border-[#CADBFA]"
          }`}
        >
          {step === 2 ? (
            <>
              <Check size={10} className="text-white" />
              <span>Schema Ingested</span>
            </>
          ) : (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-[#4A7FD4] animate-pulse" />
              <span>Scanning Schema</span>
            </>
          )}
        </span>
      </div>

      {/* Relational Schema Canvas - Clean Single Ingested Table */}
      <div className="relative">
        <div className="bg-white border border-[#CADBFA] rounded-lg p-2.5 shadow-2xs transition-all duration-300">
          <div className="flex items-center justify-between pb-1.5 mb-1.5 border-b border-[#F0F4FA] text-[10px]">
            <div className="flex items-center gap-1.5 font-bold text-[#34434C]">
              <Table size={11} className="text-[#4A7FD4]" />
              <span>customers</span>
            </div>
            <span className="text-[8px] font-mono text-[#7D97B5] bg-[#E8EFFB]/70 px-1.5 py-0.5 rounded">
              Primary Table
            </span>
          </div>

          <div className="space-y-1 font-mono text-[10px]">
            {/* id row (PK) */}
            <div
              className={`flex items-center justify-between px-1.5 py-0.5 rounded transition-all duration-500 ${
                step >= 1
                  ? "bg-[#4A7FD4]/15 text-[#1E3F7A] font-bold border border-[#4A7FD4]/30 shadow-2xs"
                  : "text-[#4A5568]"
              }`}
            >
              <span className="flex items-center gap-1">
                <KeyRound size={9} className={step >= 1 ? "text-[#4A7FD4]" : "text-[#7D97B5]"} />
                <span>id</span>
              </span>
              <span className="text-[8px] text-[#4A7FD4] font-sans font-bold">INT (PK)</span>
            </div>

            {/* other columns */}
            <div
              className={`flex items-center justify-between px-1.5 py-0.5 text-[#687985] transition-opacity duration-300 ${
                step >= 1 ? "opacity-100" : "opacity-30"
              }`}
            >
              <span>name</span>
              <span className="text-[8px] text-[#9AA8B2] font-sans">VARCHAR</span>
            </div>
            <div
              className={`flex items-center justify-between px-1.5 py-0.5 text-[#687985] transition-opacity duration-300 ${
                step >= 1 ? "opacity-100" : "opacity-30"
              }`}
            >
              <span>country</span>
              <span className="text-[8px] text-[#9AA8B2] font-sans">VARCHAR</span>
            </div>
            <div
              className={`flex items-center justify-between px-1.5 py-0.5 text-[#687985] transition-opacity duration-300 ${
                step >= 2 ? "opacity-100" : "opacity-30"
              }`}
            >
              <span>status</span>
              <span className="text-[8px] text-[#9AA8B2] font-sans">VARCHAR</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
