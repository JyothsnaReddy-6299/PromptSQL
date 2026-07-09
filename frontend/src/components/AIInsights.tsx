import { Brain, Sparkles, CheckCircle2, TrendingUp, AlertCircle } from "lucide-react";

interface Props {
  columns?: string[];
  records?: Record<string, any>[];
  missing?: number;
  rows?: number;
}

export default function AIInsights({
  columns = [],
  records = [],
  missing = 0,
  rows = 0
}: Props) {
  const generateDynamicInsights = () => {
    const list: { text: string; icon: React.ReactNode; color: string }[] = [];

    if (records.length === 0 || columns.length === 0) {
      return [
        {
          text: "Upload a dataset to generate automatic AI structure insights.",
          icon: <Brain className="text-warmgray-450" size={16} />,
          color: "bg-warmgray-50 border-warmgray-200 text-warmgray-850"
        }
      ];
    }

    list.push({
      text: `Ingested tabular schema with ${columns.length} columns and ${rows.toLocaleString()} rows. Table is fully indexed in MySQL database.`,
      icon: <CheckCircle2 className="text-emerald-500" size={16} />,
      color: "bg-emerald-50/40 border-emerald-100/50 text-emerald-800"
    });

    if (missing > 0) {
      list.push({
        text: `Cleaned ${missing.toLocaleString()} missing values across cells. Substituted blank parameters with MySQL safe NULL descriptors to maintain mathematical query alignment.`,
        icon: <AlertCircle className="text-terracotta-500 animate-pulse" size={16} />,
        color: "bg-terracotta-50/40 border-terracotta-100/50 text-terracotta-800"
      });
    } else {
      list.push({
        text: "Clean dataset with 0 missing cells detected. Schema constraints verified for numerical and textual types.",
        icon: <CheckCircle2 className="text-terracotta-500" size={16} />,
        color: "bg-terracotta-50/40 border-terracotta-100/50 text-terracotta-800"
      });
    }

    const numericCols = columns.filter(col => {
      const val = records[0][col];
      return typeof val === "number" || (!isNaN(parseFloat(val)) && isFinite(val));
    });
    
    if (numericCols.length > 0) {
      list.push({
        text: `Identified candidate key aggregates: [${numericCols.slice(0, 3).join(", ")}]. You can ask sum, average, min, or max queries on these columns.`,
        icon: <TrendingUp className="text-terracotta-600" size={16} />,
        color: "bg-sand-100/50 border-sand-200/50 text-warmgray-900"
      });
    }

    const catCols = columns.filter(col => !numericCols.includes(col));
    if (catCols.length > 0 && numericCols.length > 0) {
      const cat = catCols[0];
      const num = numericCols[0];
      
      const counts: Record<string, number> = {};
      records.forEach(r => {
        const key = String(r[cat] ?? "Other");
        const val = parseFloat(r[num]);
        counts[key] = (counts[key] || 0) + (isNaN(val) ? 0 : val);
      });
      
      const topCat = Object.entries(counts).sort((a,b) => b[1] - a[1])[0];
      if (topCat && topCat[0] !== "undefined" && topCat[0] !== "null") {
        list.push({
          text: `Distribution spike: Category "${topCat[0]}" holds the highest cumulative volume of "${num}" at ${topCat[1].toLocaleString()} inside the dataset.`,
          icon: <Sparkles className="text-terracotta-400" size={16} />,
          color: "bg-terracotta-50/40 border-terracotta-150/40 text-terracotta-800"
        });
      }
    }

    return list;
  };

  const insightsList = generateDynamicInsights();

  return (
    <div id="insights" className="bg-white rounded-2xl border border-warmgray-100 p-4 shadow-sm">
      <div className="flex items-center gap-2.5 mb-4">
        <div className="bg-terracotta-50 border border-terracotta-100 p-2 rounded-xl text-terracotta-600">
          <Brain size={18} className="text-terracotta-500" />
        </div>
        <div>
          <h2 className="text-base font-bold text-warmgray-900">
            AI Automated Insights
          </h2>
          <p className="text-warmgray-500 text-[10px] font-semibold">
            Initial schema analysis and distributions for the uploaded dataset
          </p>
        </div>
      </div>

      <div className="space-y-3">
        {insightsList.map((ins, idx) => (
          <div
            key={idx}
            className={`border rounded-xl p-3 flex gap-3 items-start ${ins.color}`}
          >
            <div className="mt-0.5 shrink-0">
              {ins.icon}
            </div>
            <p className="text-[11px] font-semibold leading-relaxed">
              {ins.text}
            </p>
          </div>
        ))}
      </div>
    </div>
  );
}