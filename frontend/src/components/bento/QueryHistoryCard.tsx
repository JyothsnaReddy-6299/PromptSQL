import { useState, useEffect, useRef } from "react";
import { History, Download, FileSpreadsheet, FileText, Check, Search, Clock } from "lucide-react";

interface HistoryItem {
  id: string;
  query: string;
  rows: number;
  time: string;
  timestamp: string;
}

const HISTORY_ITEMS: HistoryItem[] = [
  {
    id: "q1",
    query: "Show revenue by product category for Q4 2026",
    rows: 14,
    time: "0.28s",
    timestamp: "10 mins ago",
  },
  {
    id: "q2",
    query: "Find high-value accounts with total spend > $10,000",
    rows: 48,
    time: "0.34s",
    timestamp: "1 hour ago",
  },
  {
    id: "q3",
    query: "Average delivery and fulfillment latency by courier region",
    rows: 6,
    time: "0.19s",
    timestamp: "3 hours ago",
  },
];

export default function QueryHistoryCard() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [isVisible, setIsVisible] = useState(true);

  // Active highlighted card index in sequence (0, 1, 2)
  const [highlightIdx, setHighlightIdx] = useState(0);
  const [exportingId, setExportingId] = useState<string | null>("q1-csv");

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
    if (prefersReducedMotion) return;

    const timer = setInterval(() => {
      setHighlightIdx((prev) => {
        const next = (prev + 1) % HISTORY_ITEMS.length;
        setExportingId(`${HISTORY_ITEMS[next].id}-csv`);
        return next;
      });
    }, 1800);

    return () => clearInterval(timer);
  }, [isVisible]);

  return (
    <div
      ref={containerRef}
      className="w-full bg-gradient-to-br from-[#EAF2F5]/90 via-[#F3F7F8] to-[#EAF2F5]/50 border border-[#DFE7EA] rounded-xl p-3 sm:p-3.5 relative shadow-2xs"
    >
      {/* Top Controls Row */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 mb-2.5 border-b border-[#DFE7EA]">
        <div className="flex items-center gap-2">
          <div className="w-7 h-7 rounded-lg bg-white border border-[#DFE7EA] text-[#70A9AA] flex items-center justify-center shadow-2xs">
            <History size={13} />
          </div>
          <div>
            <span className="font-bold text-xs text-[#34434C] block leading-tight">
              Session Query History & Audit Trail
            </span>
            <span className="text-[9px] text-[#687985]">Persistent historical log with 1-click reporting</span>
          </div>
        </div>

        {/* Search Mockup */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 bg-white border border-[#DFE7EA] px-2.5 py-1 rounded-lg text-xs text-[#687985] w-full sm:w-56 shadow-2xs">
            <Search size={12} className="text-[#9AA8B2]" />
            <input
              type="text"
              readOnly
              placeholder="Search session queries..."
              className="bg-transparent border-none outline-none text-[10px] text-[#34434C] w-full placeholder:text-[#9AA8B2]"
            />
          </div>
        </div>
      </div>

      {/* History Items Grid */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-2.5">
        {HISTORY_ITEMS.map((item, idx) => {
          const isFocused = highlightIdx === idx;
          const isExported = exportingId === `${item.id}-csv`;

          return (
            <div
              key={item.id}
              onClick={() => {
                setHighlightIdx(idx);
                setExportingId(`${item.id}-csv`);
              }}
              className={`bg-white rounded-lg p-2.5 border transition-all duration-500 cursor-pointer flex flex-col justify-between shadow-2xs ${
                isFocused
                  ? "border-[#70A9AA] ring-1 ring-[#70A9AA]/20 -translate-y-0.5 shadow-sm"
                  : "border-[#DFE7EA] hover:border-[#70A9AA]/40"
              }`}
            >
              <div>
                <div className="flex items-center justify-between text-[9px] text-[#8C9BA5] mb-1.5 font-mono">
                  <span className="flex items-center gap-1">
                    <Clock size={9} />
                    <span>{item.timestamp}</span>
                  </span>
                  <span
                    className={`font-semibold transition-colors duration-300 ${
                      isFocused ? "text-[#70A9AA]" : "text-[#8C9BA5]"
                    }`}
                  >
                    {item.time}
                  </span>
                </div>
                <p className="text-[11px] font-semibold text-[#34434C] line-clamp-2 mb-2 leading-snug">
                  "{item.query}"
                </p>
              </div>

              <div className="pt-2 border-t border-[#F0F4F6] flex items-center justify-between">
                <span className="text-[9px] text-[#687985] font-mono">
                  {item.rows} rows returned
                </span>

                {/* Animated Export Action Buttons */}
                <div className="flex items-center gap-1">
                  <span
                    className={`flex items-center gap-1 text-[9px] font-semibold px-1.5 py-0.5 rounded border transition-all duration-300 ${
                      isExported
                        ? "bg-[#E1F0EF] text-[#2B5758] border-[#C2E4E2]"
                        : "bg-[#F0F4F6] text-[#475569] border-[#DFE7EA]"
                    }`}
                  >
                    {isExported ? <Check size={10} className="text-[#70A9AA]" /> : <FileSpreadsheet size={10} />}
                    <span>CSV</span>
                  </span>

                  <span className="flex items-center gap-1 text-[9px] font-medium bg-[#F0F4F6] text-[#475569] border border-[#DFE7EA] px-1.5 py-0.5 rounded">
                    <FileText size={10} />
                    <span>PDF</span>
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Footer Strip */}
      <div className="mt-2.5 pt-2 border-t border-[#DFE7EA] flex flex-wrap items-center justify-between text-[10px] text-[#687985]">
        <div className="flex items-center gap-1.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#70A9AA]" />
          <span>Full immutable query logging with execution latency & affected row counts</span>
        </div>
        <div className="flex items-center gap-1 text-[#70A9AA] font-semibold text-[9px] uppercase tracking-wider">
          <Download size={10} />
          <span>Instant One-Click Export Engine</span>
        </div>
      </div>
    </div>
  );
}
