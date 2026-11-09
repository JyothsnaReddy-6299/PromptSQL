import { useState, useEffect, useRef } from "react";
import { ShieldCheck, Check, Lock, Terminal } from "lucide-react";

export default function QueryValidationCard() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(true);

  // Step 0: SQL loaded, checks idle
  // Step 1: Syntax Valid
  // Step 2: Schema Approved
  // Step 3: Sandbox Enforced
  // Step 4: Execution Permitted
  const [step, setStep] = useState<0 | 1 | 2 | 3 | 4>(0);

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
      setStep(4);
      return;
    }

    let timer: ReturnType<typeof setTimeout>;

    if (step === 0) {
      timer = setTimeout(() => setStep(1), 280);
    } else if (step === 1) {
      timer = setTimeout(() => setStep(2), 320);
    } else if (step === 2) {
      timer = setTimeout(() => setStep(3), 320);
    } else if (step === 3) {
      timer = setTimeout(() => setStep(4), 320);
    } else if (step === 4) {
      timer = setTimeout(() => setStep(0), 2200);
    }

    return () => clearTimeout(timer);
  }, [isVisible, step]);

  return (
    <div
      ref={containerRef}
      className="w-full bg-gradient-to-br from-[#F0EAF9]/85 via-[#F7F3FB] to-[#F0EAF9]/50 border border-[#DCCEF2] rounded-xl p-3 sm:p-3.5 relative shadow-2xs"
    >
      {/* Top Header */}
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#DCCEF2] text-xs">
        <div className="flex items-center gap-1.5 font-bold text-[#34434C] text-[11px]">
          <ShieldCheck size={13} className="text-[#7D52B8]" />
          <span>AST Safety Guardrails</span>
        </div>
        <span
          className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border transition-all duration-300 ${
            step === 4
              ? "bg-[#7D52B8] text-white border-[#7D52B8] shadow-2xs"
              : "bg-white text-[#7D52B8] border-[#DCCEF2]"
          }`}
        >
          {step === 4 ? "Execution Permitted" : "AST Validating..."}
        </span>
      </div>

      {/* Code Snippet Box (Clean Slate Inset) */}
      <div className="bg-[#172832] text-white rounded-lg p-2.5 font-mono text-[10px] mb-2 border border-[#2F4A58] shadow-xs">
        <div className="flex items-center justify-between text-[9px] text-[#A5BAC6] pb-1 mb-1 border-b border-[#2F4A58]/70">
          <span className="flex items-center gap-1.5 text-[#8BC5C5]">
            <Terminal size={10} />
            <span>parameterized_query.sql</span>
          </span>
          <span className="text-[#8BC5C5] bg-[#223B47] px-1.5 py-0.5 rounded text-[8px]">Safe Parameterized</span>
        </div>
        <div className="text-[#DFEBF2] leading-snug">
          <span className="text-[#8BC5C5] font-semibold">SELECT</span> id, amount, status<br />
          <span className="text-[#8BC5C5] font-semibold">FROM</span> transactions<br />
          <span className="text-[#8BC5C5] font-semibold">WHERE</span> user_id = <span className="text-[#9AE6B4]">:auth_uid</span>;
        </div>
      </div>

      {/* Validation Pipeline Checkpoints with Sequential Checkmark Animation */}
      <div className="space-y-1">
        {/* Step 1: Syntax & AST Parser */}
        <div
          className={`bg-white rounded-lg px-2.5 py-1.5 border transition-all duration-300 flex items-center justify-between text-[10px] shadow-2xs ${
            step >= 1 ? "border-emerald-300 bg-emerald-50/20" : "border-[#DCCEF2]"
          }`}
        >
          <span className="text-[#34434C] font-semibold flex items-center gap-1.5">
            <span
              className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] transition-all duration-300 ${
                step >= 1 ? "bg-emerald-100 text-emerald-700" : "bg-[#F0EAF9] text-[#A5BAC6]"
              }`}
            >
              {step >= 1 ? <Check size={9} /> : <span className="w-1 h-1 rounded-full bg-[#A5BAC6]" />}
            </span>
            <span>Syntax & AST Parser</span>
          </span>
          <span
            className={`text-[9px] font-mono font-bold transition-all duration-300 ${
              step >= 1 ? "text-emerald-600 scale-100" : "text-[#A5BAC6] scale-95"
            }`}
          >
            {step >= 1 ? "VALID" : "PENDING"}
          </span>
        </div>

        {/* Step 2: Schema Authorization */}
        <div
          className={`bg-white rounded-lg px-2.5 py-1.5 border transition-all duration-300 flex items-center justify-between text-[10px] shadow-2xs ${
            step >= 2 ? "border-emerald-300 bg-emerald-50/20" : "border-[#DCCEF2]"
          }`}
        >
          <span className="text-[#34434C] font-semibold flex items-center gap-1.5">
            <span
              className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] transition-all duration-300 ${
                step >= 2 ? "bg-emerald-100 text-emerald-700" : "bg-[#F0EAF9] text-[#A5BAC6]"
              }`}
            >
              {step >= 2 ? <Check size={9} /> : <span className="w-1 h-1 rounded-full bg-[#A5BAC6]" />}
            </span>
            <span>Schema Authorization</span>
          </span>
          <span
            className={`text-[9px] font-mono font-bold transition-all duration-300 ${
              step >= 2 ? "text-emerald-600 scale-100" : "text-[#A5BAC6] scale-95"
            }`}
          >
            {step >= 2 ? "APPROVED" : "PENDING"}
          </span>
        </div>

        {/* Step 3: Read-Only Constraint */}
        <div
          className={`bg-white rounded-lg px-2.5 py-1.5 border transition-all duration-300 flex items-center justify-between text-[10px] shadow-2xs ${
            step >= 3 ? "border-[#7D52B8]/40 bg-[#F0EAF9]/30" : "border-[#DCCEF2]"
          }`}
        >
          <span className="text-[#34434C] font-semibold flex items-center gap-1.5">
            <span
              className={`w-3.5 h-3.5 rounded-full flex items-center justify-center text-[9px] transition-all duration-300 ${
                step >= 3 ? "bg-[#F0EAF9] text-[#7D52B8]" : "bg-[#F0EAF9] text-[#A5BAC6]"
              }`}
            >
              {step >= 3 ? <Lock size={9} /> : <span className="w-1 h-1 rounded-full bg-[#A5BAC6]" />}
            </span>
            <span>Read-Only Constraint</span>
          </span>
          <span
            className={`text-[9px] font-mono font-bold transition-all duration-300 ${
              step >= 3 ? "text-[#7D52B8] scale-100" : "text-[#A5BAC6] scale-95"
            }`}
          >
            {step >= 3 ? "ENFORCED" : "PENDING"}
          </span>
        </div>
      </div>

      {/* Final Execution Status */}
      <div className="mt-2 pt-2 border-t border-[#DCCEF2] flex items-center justify-between text-[10px]">
        <div className="flex items-center gap-1.5 font-semibold text-[#34434C]">
          <span
            className={`w-1.5 h-1.5 rounded-full transition-all duration-300 ${
              step === 4 ? "bg-emerald-500 animate-pulse" : "bg-amber-400"
            }`}
          />
          <span>{step === 4 ? "Execution Permitted" : "Pre-Execution Analysis"}</span>
        </div>
        <span className="text-[9px] font-mono text-[#687985]">0 Injection Risk</span>
      </div>
    </div>
  );
}
