import { useState, useEffect } from "react";
import { Layers, Grid, AlertTriangle, Cpu } from "lucide-react";

interface Props {
  rows?: number;
  columns?: number;
  missing?: number;
  size?: string;
  detectedTypes?: Record<string, string>;
}

function CountUp({ end, duration = 1200 }: { end: number; duration?: number }) {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let startTimestamp: number | null = null;
    let animFrameId: number;

    const step = (timestamp: number) => {
      if (!startTimestamp) startTimestamp = timestamp;
      const progress = Math.min((timestamp - startTimestamp) / duration, 1);
      setCount(Math.floor(progress * end));
      if (progress < 1) {
        animFrameId = window.requestAnimationFrame(step);
      }
    };

    animFrameId = window.requestAnimationFrame(step);
    return () => window.cancelAnimationFrame(animFrameId);
  }, [end, duration]);

  return <>{count.toLocaleString()}</>;
}

export default function KPICards({
  rows = 0,
  columns = 0,
  missing = 0,
  size = "N/A",
  detectedTypes = {},
}: Props) {
  const typeList = Object.values(detectedTypes);
  const numCols = typeList.filter((t) => t.toLowerCase() === "numeric" || t.toLowerCase() === "int" || t.toLowerCase() === "float" || t.toLowerCase() === "double" || t.toLowerCase() === "decimal").length;
  const textCols = typeList.filter((t) => t.toLowerCase() === "text" || t.toLowerCase() === "varchar").length;
  const dateCols = typeList.filter((t) => t.toLowerCase() === "date" || t.toLowerCase() === "datetime" || t.toLowerCase() === "timestamp").length;

  const cardData = [
    {
      title: "Total Rows",
      value: <CountUp end={rows} />,
      desc: `${rows > 1000 ? (rows / 1000).toFixed(1) + "k" : rows} records`,
      icon: <Layers size={16} />,
      iconColor: "text-[#76ABAE]",
      iconBg: "bg-[#76ABAE]/10 border-[#76ABAE]/20",
      badge: "Loaded",
      badgeColor: "text-[#76ABAE] bg-[#76ABAE]/10 border-[#76ABAE]/30",
    },
    {
      title: "Schema Columns",
      value: <CountUp end={columns} />,
      desc: `${numCols} numeric · ${textCols} text` + (dateCols > 0 ? ` · ${dateCols} date` : ""),
      icon: <Grid size={16} />,
      iconColor: "text-[#76ABAE]",
      iconBg: "bg-[#76ABAE]/10 border-[#76ABAE]/20",
      badge: `${columns} fields`,
      badgeColor: "text-[#76ABAE] bg-[#76ABAE]/10 border-[#76ABAE]/30",
    },
    {
      title: "Missing Cells",
      value: <CountUp end={missing} />,
      desc: missing > 0 ? `${((missing / (rows * columns || 1)) * 100).toFixed(1)}% empty` : "No nulls found",
      icon: <AlertTriangle size={16} />,
      iconColor: missing > 0 ? "text-[#FF5722]" : "text-[#76ABAE]",
      iconBg: missing > 0 ? "bg-[#FF5722]/10 border-[#FF5722]/20" : "bg-[#76ABAE]/10 border-[#76ABAE]/20",
      badge: missing > 0 ? "Needs cleaning" : "Complete",
      badgeColor: missing > 0 ? "text-[#FF5722] bg-[#FF5722]/10 border-[#FF5722]/30" : "text-[#76ABAE] bg-[#76ABAE]/10 border-[#76ABAE]/30",
    },
    {
      title: "Data Footprint",
      value: size || "N/A",
      desc: "In-memory dataset size",
      icon: <Cpu size={16} />,
      iconColor: "text-[#76ABAE]",
      iconBg: "bg-[#76ABAE]/10 border-[#76ABAE]/20",
      badge: "Optimized",
      badgeColor: "text-[#76ABAE] bg-[#76ABAE]/10 border-[#76ABAE]/30",
    },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cardData.map((card, idx) => (
        <div
          key={idx}
          className="relative bg-white border border-gray-200/80 rounded-xl p-5 shadow-sm hover:shadow-md transition-all duration-300 overflow-hidden"
        >
          <div className="flex justify-between items-start mb-4">
            <p className="text-[11px] font-semibold text-[#4A5568] uppercase tracking-wider">
              {card.title}
            </p>
            <div className={`w-8 h-8 ${card.iconBg} border rounded-lg flex items-center justify-center ${card.iconColor}`}>
              {card.icon}
            </div>
          </div>

          <h2 className="text-3xl font-bold text-[#303841] tracking-tight leading-none mb-3">
            {card.value}
          </h2>

          <div className="flex items-center justify-between">
            <span className="text-xs text-[#4A5568]">{card.desc}</span>
            <span className={`text-[10px] font-semibold px-2 py-0.5 rounded-full border ${card.badgeColor}`}>
              {card.badge}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}
