import { useState } from "react";
import { BarChart3, TrendingUp, HelpCircle } from "lucide-react";

interface Props {
  columns?: string[];
  records?: Record<string, any>[];
  loading?: boolean;
}

export default function ChartsSection({
  columns = [],
  records = [],
  loading = false
}: Props) {
  const [chartType, setChartType] = useState<"bar" | "line">("bar");

  const getVisualSpecs = () => {
    if (records.length === 0 || columns.length === 0) return null;

    const numericCol = columns.find(col => {
      const sampleVal = records[0][col];
      return typeof sampleVal === "number" || (!isNaN(parseFloat(sampleVal)) && isFinite(sampleVal));
    });

    const categoricalCol = columns.find(col => col !== numericCol);

    if (!numericCol || !categoricalCol) return null;

    const groups: Record<string, number> = {};
    records.forEach(row => {
      const label = String(row[categoricalCol] ?? "Other");
      const val = parseFloat(row[numericCol]);
      const cleanVal = isNaN(val) ? 0 : val;
      groups[label] = (groups[label] || 0) + cleanVal;
    });

    const sorted = Object.entries(groups)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 6);

    const labels = sorted.map(item => item[0]);
    const values = sorted.map(item => item[1]);

    return {
      labels,
      values,
      numericCol,
      categoricalCol
    };
  };

  const specs = getVisualSpecs();

  if (!specs || records.length === 0) {
    return (
      <div id="charts" className="bg-white border border-warmgray-100 rounded-2xl p-4 shadow-sm">
        <h2 className="text-base font-bold text-warmgray-900 mb-4 flex items-center gap-2">
          <BarChart3 className="text-warmgray-400" size={18} /> Visualizations
        </h2>
        <div className="h-48 flex flex-col items-center justify-center text-warmgray-400 border border-dashed border-warmgray-100 rounded-xl p-4">
          <HelpCircle size={24} className="text-warmgray-300 mb-1" />
          <p className="text-xs font-bold text-warmgray-850">Visualizations are generated after loading data.</p>
          <p className="text-[10px] text-warmgray-450 mt-0.5">Ensure your dataset has categorical and numerical fields.</p>
        </div>
      </div>
    );
  }

  const { labels, values, numericCol, categoricalCol } = specs;
  const maxValue = Math.max(...values, 1);
  const minValue = Math.min(...values, 0);
  const range = maxValue - minValue;

  const width = 500;
  const height = 180;
  const paddingLeft = 70;
  const paddingRight = 15;
  const paddingTop = 15;
  const paddingBottom = 35;

  const graphWidth = width - paddingLeft - paddingRight;
  const graphHeight = height - paddingTop - paddingBottom;

  const points = values.map((val, idx) => {
    const x = paddingLeft + idx * (graphWidth / (values.length - 1 || 1));
    const ratio = range === 0 ? 0.5 : (val - minValue) / range;
    const y = paddingTop + graphHeight - ratio * graphHeight;
    return { x, y, label: labels[idx], value: val };
  });

  return (
    <div id="charts" className="bg-white border border-warmgray-100 rounded-2xl p-4 shadow-sm">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-3 mb-4">
        <div>
          <h2 className="text-base font-bold text-warmgray-900 flex items-center gap-2">
            <BarChart3 className="text-terracotta-500" size={18} />
            <span>Dataset Distribution</span>
          </h2>
          <p className="text-[10px] mt-0.5 font-bold text-warmgray-500">
            Auto-aggregated sum of <span className="text-warmgray-850">{numericCol}</span> grouped by <span className="text-warmgray-850">{categoricalCol}</span> (Top {labels.length})
          </p>
        </div>

        <div className="flex border border-warmgray-200 rounded-lg overflow-hidden self-end sm:self-auto shrink-0 bg-warmgray-50 p-0.5">
          <button
            onClick={() => setChartType("bar")}
            className={`px-2.5 py-1.5 rounded-md text-[10px] font-bold transition cursor-pointer flex items-center gap-1.5 ${
              chartType === "bar" ? "bg-white text-warmgray-950 shadow-sm border border-warmgray-200/50" : "text-warmgray-500 hover:text-warmgray-800"
            }`}
          >
            <BarChart3 size={10} className="text-terracotta-500" /> Bar
          </button>
          <button
            onClick={() => setChartType("line")}
            className={`px-2.5 py-1.5 rounded-md text-[10px] font-bold transition cursor-pointer flex items-center gap-1.5 ${
              chartType === "line" ? "bg-white text-warmgray-955 shadow-sm border border-warmgray-200/50" : "text-warmgray-500 hover:text-warmgray-800"
            }`}
          >
            <TrendingUp size={10} className="text-terracotta-500" /> Line
          </button>
        </div>
      </div>

      {loading ? (
        <div className="h-48 flex items-center justify-center">
          <div className="w-6 h-6 border-2 border-terracotta-500 border-t-transparent rounded-full animate-spin" />
        </div>
      ) : (
        <div className="flex justify-center p-2 border border-warmgray-100 bg-warmgray-50/50 rounded-xl">
          <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className="max-w-[500px]">
            {/* Gridlines & Y axis labels */}
            {[0, 0.25, 0.5, 0.75, 1].map((ratio, gridIdx) => {
              const y = paddingTop + graphHeight - ratio * graphHeight;
              const gridVal = minValue + ratio * range;
              return (
                <g key={gridIdx}>
                  <line
                    x1={paddingLeft}
                    y1={y}
                    x2={width - paddingRight}
                    y2={y}
                    stroke="#e8e2da"
                    strokeWidth="1"
                    strokeDasharray="4 4"
                  />
                  <text
                    x={paddingLeft - 10}
                    y={y + 3}
                    textAnchor="end"
                    fill="#bd9f8d"
                    fontSize="8"
                    fontFamily="monospace"
                    fontWeight="bold"
                  >
                    {gridVal >= 1000000 
                      ? (gridVal / 1000000).toFixed(1) + "M"
                      : gridVal >= 1000
                      ? (gridVal / 1000).toFixed(0) + "k"
                      : gridVal.toFixed(0)}
                  </text>
                </g>
              );
            })}

            {/* Bar rendering */}
            {chartType === "bar" &&
              points.map((pt, barIdx) => {
                const barWidth = Math.max(graphWidth / points.length * 0.5, 10);
                const barX = pt.x - barWidth / 2;
                const barY = pt.y;
                const barHeight = paddingTop + graphHeight - pt.y;

                return (
                  <g key={barIdx} className="group">
                    <rect
                      x={barX}
                      y={barY}
                      width={barWidth}
                      height={Math.max(barHeight, 2)}
                      rx="3"
                      className="fill-terracotta-500/80 hover:fill-terracotta-600 transition-all duration-300 shadow"
                    />
                    <title>{`${pt.label}: ${pt.value.toLocaleString()}`}</title>
                    <text
                      x={pt.x}
                      y={height - 18}
                      textAnchor="middle"
                      fill="#a07f6b"
                      fontSize="8"
                      fontWeight="bold"
                      transform={`rotate(-15, ${pt.x}, ${height - 18})`}
                    >
                      {pt.label.length > 9 ? pt.label.slice(0, 8) + ".." : pt.label}
                    </text>
                  </g>
                );
              })}

            {/* Line rendering */}
            {chartType === "line" && (
              <g>
                {/* Gradient area */}
                <defs>
                  <linearGradient id="distGradBig" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stopColor="#C35237" stopOpacity="0.25" />
                    <stop offset="100%" stopColor="#C35237" stopOpacity="0.0" />
                  </linearGradient>
                </defs>
                <path
                  d={`${points.map((pt, idx) => `${idx === 0 ? "M" : "L"} ${pt.x} ${pt.y}`).join(" ")} L ${points[points.length-1].x} ${paddingTop+graphHeight} L ${points[0].x} ${paddingTop+graphHeight} Z`}
                  fill="url(#distGradBig)"
                />

                {/* Main line path */}
                <path
                  d={points.map((pt, idx) => `${idx === 0 ? "M" : "L"} ${pt.x} ${pt.y}`).join(" ")}
                  fill="none"
                  stroke="#C35237"
                  strokeWidth="2.5"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />

                {/* Dots */}
                {points.map((pt, idx) => (
                  <g key={idx} className="group">
                    <circle
                      cx={pt.x}
                      cy={pt.y}
                      r="4"
                      className="fill-white stroke-terracotta-650 stroke-2 hover:fill-terracotta-700 transition-all"
                    />
                    <title>{`${pt.label}: ${pt.value.toLocaleString()}`}</title>
                    <text
                      x={pt.x}
                      y={height - 18}
                      textAnchor="middle"
                      fill="#a07f6b"
                      fontSize="8"
                      fontWeight="bold"
                      transform={`rotate(-15, ${pt.x}, ${height - 18})`}
                    >
                      {pt.label.length > 9 ? pt.label.slice(0, 8) + ".." : pt.label}
                    </text>
                  </g>
                ))}
              </g>
            )}
          </svg>
        </div>
      )}
    </div>
  );
}