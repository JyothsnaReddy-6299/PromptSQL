import { useState, useEffect, useRef } from "react";
import { CheckCircle2, AlertTriangle, Wand2, RefreshCw } from "lucide-react";

export default function DataCleaningCard() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(true);

  // Step 0: Raw issues detected (score 74%)
  // Step 1: Scanning / Auto-imputing in progress
  // Step 2: Issues resolved (score animates to 99%)
  const [step, setStep] = useState<0 | 1 | 2>(0);
  const [score, setScore] = useState(74);

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
      setScore(99);
      return;
    }

    let timer: ReturnType<typeof setTimeout>;

    if (step === 0) {
      setScore(74);
      timer = setTimeout(() => setStep(1), 450);
    } else if (step === 1) {
      timer = setTimeout(() => {
        setStep(2);
        // Animate score counter upwards rapidly
        const interval = setInterval(() => {
          setScore((prev) => {
            if (prev >= 99) {
              clearInterval(interval);
              return 99;
            }
            return prev + 4;
          });
        }, 16);
      }, 550);
    } else if (step === 2) {
      timer = setTimeout(() => {
        setStep(0);
        setScore(74);
      }, 2200);
    }

    return () => clearTimeout(timer);
  }, [isVisible, step]);

  return (
    <div
      ref={containerRef}
      className="w-full bg-gradient-to-br from-[#FCE9E3]/80 via-[#FDF3EE] to-[#FCE9E3]/50 border border-[#F7CDBC] rounded-xl p-3 sm:p-3.5 relative shadow-2xs"
    >
      {/* Top Header / Scanner status */}
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-[#F7CDBC] text-xs">
        <div className="flex items-center gap-1.5 font-bold text-[#34434C] text-[11px]">
          <Wand2 size={13} className="text-[#DE6846]" />
          <span>Automated Preprocessing Suite</span>
        </div>

        <div className="flex items-center gap-1.5 text-[9px] font-semibold bg-white px-2 py-0.5 rounded-full border border-[#F7CDBC] shadow-2xs">
          {step === 1 ? (
            <>
              <RefreshCw size={9} className="text-[#DE6846] animate-spin" />
              <span className="text-[#DE6846]">Auto-Healing...</span>
            </>
          ) : step === 2 ? (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              <span className="text-emerald-700">100% Query Ready</span>
            </>
          ) : (
            <>
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500 animate-pulse" />
              <span className="text-amber-700">3 Anomalies Flagged</span>
            </>
          )}
        </div>
      </div>

      {/* Dataset Health Score Box */}
      <div className="bg-white rounded-lg p-2.5 border border-[#F7CDBC] mb-2 shadow-2xs">
        <div className="flex items-center justify-between text-[10px] mb-1">
          <span className="font-semibold text-[#34434C]">
            {step === 2 ? "Dataset Hygiene: Cleaned" : "Dataset Hygiene: Raw Assessment"}
          </span>
          <span
            className={`font-mono font-bold text-[11px] transition-colors duration-300 ${
              step === 2 ? "text-[#70A9AA]" : "text-amber-600"
            }`}
          >
            {score}.4%
          </span>
        </div>
        <div className="w-full h-1.5 bg-[#FCE9E3]/60 rounded-full overflow-hidden">
          <div
            style={{ width: `${score}%` }}
            className={`h-full transition-all duration-500 rounded-full ${
              step === 2 ? "bg-gradient-to-r from-[#70A9AA] to-[#8BC5C5]" : "bg-amber-400"
            }`}
          />
        </div>
      </div>

      {/* Issue Categories with animated state change */}
      <div className="space-y-1.5">
        {/* Row 1: Missing Values */}
        <div className="bg-white rounded-lg p-2 border border-[#F7CDBC] flex items-center justify-between text-[10px] shadow-2xs transition-all duration-300">
          <div className="flex items-center gap-2">
            {step === 2 ? (
              <CheckCircle2 size={13} className="text-[#70A9AA] shrink-0" />
            ) : (
              <AlertTriangle size={13} className="text-amber-500 shrink-0" />
            )}
            <div>
              <span className="font-semibold text-[#34434C] block leading-tight">Missing Values</span>
              <span className="text-[9px] text-[#687985]">
                {step === 2 ? "Auto-imputed with column median" : "14 empty numeric cells detected"}
              </span>
            </div>
          </div>
          <span
            className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border transition-all duration-300 ${
              step === 2
                ? "bg-[#E1F0EF] text-[#2B5758] border-[#C2E4E2]"
                : "bg-[#FCE9E3] text-[#A63A1A] border-[#F7CDBC]"
            }`}
          >
            {step === 2 ? "Resolved" : "14 Found"}
          </span>
        </div>

        {/* Row 2: Duplicate Records */}
        <div className="bg-white rounded-lg p-2 border border-[#F7CDBC] flex items-center justify-between text-[10px] shadow-2xs transition-all duration-300">
          <div className="flex items-center gap-2">
            {step === 2 ? (
              <CheckCircle2 size={13} className="text-[#70A9AA] shrink-0" />
            ) : (
              <AlertTriangle size={13} className="text-amber-500 shrink-0" />
            )}
            <div>
              <span className="font-semibold text-[#34434C] block leading-tight">Duplicate Records</span>
              <span className="text-[9px] text-[#687985]">
                {step === 2 ? "Deduplicated via unique keys" : "3 duplicate customer entries"}
              </span>
            </div>
          </div>
          <span
            className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border transition-all duration-300 ${
              step === 2
                ? "bg-[#E1F0EF] text-[#2B5758] border-[#C2E4E2]"
                : "bg-[#FCE9E3] text-[#A63A1A] border-[#F7CDBC]"
            }`}
          >
            {step === 2 ? "Pruned" : "3 Found"}
          </span>
        </div>

        {/* Row 3: Mixed Date Formats */}
        <div className="bg-white rounded-lg p-2 border border-[#F7CDBC] flex items-center justify-between text-[10px] shadow-2xs transition-all duration-300">
          <div className="flex items-center gap-2">
            {step === 2 ? (
              <CheckCircle2 size={13} className="text-[#70A9AA] shrink-0" />
            ) : (
              <AlertTriangle size={13} className="text-amber-500 shrink-0" />
            )}
            <div>
              <span className="font-semibold text-[#34434C] block leading-tight">Date & Type Formats</span>
              <span className="text-[9px] text-[#687985]">
                {step === 2 ? "Standardized to ISO YYYY-MM-DD" : "Mixed date text formats"}
              </span>
            </div>
          </div>
          <span
            className={`text-[9px] font-semibold px-2 py-0.5 rounded-full border transition-all duration-300 ${
              step === 2
                ? "bg-[#E1F0EF] text-[#2B5758] border-[#C2E4E2]"
                : "bg-[#FCE9E3] text-[#A63A1A] border-[#F7CDBC]"
            }`}
          >
            {step === 2 ? "Standardized" : "Mismatch"}
          </span>
        </div>
      </div>
    </div>
  );
}
