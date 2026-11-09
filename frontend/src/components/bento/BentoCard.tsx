import type { ReactNode } from "react";

interface BentoCardProps {
  badge?: string;
  title: string;
  description: string;
  icon?: ReactNode;
  accentColor?: "teal" | "blue" | "peach" | "lavender" | "slate";
  className?: string;
  children?: ReactNode;
}

export default function BentoCard({
  badge,
  title,
  description,
  icon,
  accentColor = "teal",
  className = "",
  children,
}: BentoCardProps) {
  // Pastel badge & icon styling presets
  const colorMap = {
    teal: {
      icon: "bg-[#E1F0EF] text-[#70A9AA] border-[#C2E4E2]",
      badge: "bg-[#E1F0EF]/80 text-[#2B5758] border-[#C2E4E2]",
    },
    blue: {
      icon: "bg-[#E8EFFB] text-[#4A7FD4] border-[#CADBFA]",
      badge: "bg-[#E8EFFB]/80 text-[#2C5294] border-[#CADBFA]",
    },
    peach: {
      icon: "bg-[#FCE9E3] text-[#DE6846] border-[#F7CDBC]",
      badge: "bg-[#FCE9E3]/80 text-[#A63A1A] border-[#F7CDBC]",
    },
    lavender: {
      icon: "bg-[#F0EAF9] text-[#7D52B8] border-[#DCCEF2]",
      badge: "bg-[#F0EAF9]/80 text-[#543085] border-[#DCCEF2]",
    },
    slate: {
      icon: "bg-[#EAF2F5] text-[#556976] border-[#DFE7EA]",
      badge: "bg-[#EAF2F5]/80 text-[#34434C] border-[#DFE7EA]",
    },
  }[accentColor];

  return (
    <div
      className={`group relative bg-white border border-[#DFE7EA] rounded-2xl p-4.5 sm:p-5.5 flex flex-col justify-between overflow-hidden shadow-[0_3px_18px_rgba(52,67,76,0.04)] hover:shadow-[0_10px_28px_rgba(112,169,170,0.12)] hover:border-[#70A9AA]/50 transition-all duration-300 ease-out hover:-translate-y-1 motion-reduce:hover:translate-y-0 ${className}`}
    >
      {/* Subtle ambient pastel glow in corner */}
      <div className="pointer-events-none absolute -top-10 -right-10 w-36 h-36 rounded-full bg-gradient-to-br from-[#70A9AA]/8 to-transparent blur-xl group-hover:scale-125 transition-transform duration-500" />

      {/* Header Info */}
      <div className="relative z-10 mb-4">
        <div className="flex items-center justify-between gap-2.5 mb-2.5">
          {icon && (
            <div
              className={`w-9 h-9 rounded-xl flex items-center justify-center border shadow-2xs transition-all duration-300 group-hover:scale-105 ${colorMap.icon}`}
            >
              {icon}
            </div>
          )}
          {badge && (
            <span
              className={`text-[10px] font-semibold tracking-wider uppercase px-2.5 py-0.5 rounded-full border shadow-2xs ${colorMap.badge}`}
            >
              {badge}
            </span>
          )}
        </div>
        <h3 className="text-base sm:text-lg font-bold text-[#34434C] tracking-tight group-hover:text-[#1F2937] transition-colors leading-snug">
          {title}
        </h3>
        <p className="text-xs sm:text-[13px] text-[#687985] leading-relaxed mt-1.5">
          {description}
        </p>
      </div>

      {/* Demonstration / Interactive Preview */}
      <div className="relative z-10 mt-auto w-full flex-1 flex flex-col justify-end">
        {children}
      </div>
    </div>
  );
}
