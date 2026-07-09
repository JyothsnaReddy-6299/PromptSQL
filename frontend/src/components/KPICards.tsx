import { Layers, Grid, AlertTriangle, Cpu } from "lucide-react";

interface Props {
  rows?: number;
  columns?: number;
  missing?: number;
  size?: string;
  detectedTypes?: Record<string, string>;
}

export default function KPICards({
  rows = 0,
  columns = 0,
  missing = 0,
  size = "N/A",
  detectedTypes = {}
}: Props) {
  const typeList = Object.values(detectedTypes);
  const textCols = typeList.filter(t => t.toLowerCase() === "text" || t.toLowerCase() === "varchar").length;
  const numCols = typeList.length - textCols;

  const cardData = [
    {
      title: "Total Rows",
      value: rows.toLocaleString(),
      desc: "Total records",
      icon: <Layers className="text-terracotta-500" size={18} />,
      badge: `${(rows > 1000 ? (rows / 1000).toFixed(1) + "k" : rows)} rows`,
      color: "border-l-terracotta-500",
      bg: "from-terracotta-500/5 to-transparent"
    },
    {
      title: "Schema Columns",
      value: columns.toLocaleString(),
      desc: `${numCols} num, ${textCols} text`,
      icon: <Grid className="text-sand-400" size={18} />,
      badge: `${columns} fields`,
      color: "border-l-sand-400",
      bg: "from-sand-400/5 to-transparent"
    },
    {
      title: "Missing Cells",
      value: missing.toLocaleString(),
      desc: "Null or blank cells",
      icon: <AlertTriangle className={missing > 0 ? "text-terracotta-400 animate-pulse" : "text-emerald-500"} size={18} />,
      badge: missing > 0 ? `${((missing / (rows * columns || 1)) * 100).toFixed(1)}% empty` : "Complete",
      color: missing > 0 ? "border-l-terracotta-400" : "border-l-emerald-500",
      bg: missing > 0 ? "from-terracotta-400/5 to-transparent" : "from-emerald-500/5 to-transparent"
    },
    {
      title: "Data Footprint",
      value: size || "N/A",
      desc: "InMemory footprint",
      icon: <Cpu className="text-terracotta-600" size={18} />,
      badge: "Optimized",
      color: "border-l-terracotta-600",
      bg: "from-terracotta-600/5 to-transparent"
    }
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
      {cardData.map((card, idx) => (
        <div
          key={idx}
          className={`bg-white border border-warmgray-100 border-l-4 ${card.color} rounded-xl p-4 shadow-sm hover:shadow-md transition-all duration-300 relative overflow-hidden bg-gradient-to-br ${card.bg}`}
        >
          <div className="flex justify-between items-start">
            <div>
              <p className="text-[10px] font-bold text-warmgray-400 uppercase tracking-wider">
                {card.title}
              </p>
              <h2 className="text-2xl font-extrabold text-warmgray-900 tracking-tight mt-1 leading-none">
                {card.value}
              </h2>
            </div>
            <div className="bg-warmgray-50 border border-warmgray-100 p-2 rounded-lg shadow-inner shrink-0">
              {card.icon}
            </div>
          </div>
          
          <div className="mt-4 flex justify-between items-center text-[10px]">
            <span className="text-warmgray-500 font-semibold">
              {card.desc}
            </span>
            <span className={`font-bold px-2 py-0.5 rounded-full ${
              card.title.includes("Missing") && missing > 0
                ? "bg-terracotta-50 text-terracotta-700 border border-terracotta-100"
                : "bg-warmgray-50 text-warmgray-600 border border-warmgray-100"
            }`}>
              {card.badge}
            </span>
          </div>
        </div>
      ))}
    </div>
  );
}