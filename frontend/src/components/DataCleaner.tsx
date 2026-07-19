import { useState, useEffect } from "react";
import { 
  Sparkles, 
  Trash2, 
  Wand2, 
  Loader2, 
  AlertTriangle, 
  CheckCircle,
  Database,
  Type,
  Scissors,
  Activity,
  Zap
} from "lucide-react";
import { 
  cleanRemoveDuplicates, 
  cleanImpute, 
  cleanConvertType,
  cleanStandardizeText,
  cleanExtractNumbers,
  cleanCapOutliers,
  detectNumericTextColumns,
  cleanExtractAndConvert
} from "../services/api";

interface Props {
  columns: string[];
  detectedTypes: Record<string, string>;
  columnMissing: Record<string, number>;
  columnStats?: Record<string, any>;
  onRefresh: () => void;
  loading?: boolean;
}

export default function DataCleaner({
  columns = [],
  detectedTypes = {},
  columnMissing = {},
  columnStats = {},
  onRefresh,
  loading = false
}: Props) {
  const [cleaning, setCleaning] = useState(false);
  const [statusMessage, setStatusMessage] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [selectedColumn, setSelectedColumn] = useState("");
  const [suspiciousColumns, setSuspiciousColumns] = useState<Array<{ column: string; sample_values: string[]; numeric_ratio: number; name_hint: boolean }>>([]);
  const [scanningTypes, setScanningTypes] = useState(false);

  // Auto-scan for numeric-looking text columns when cleaner loads or after refresh
  useEffect(() => {
    const scan = async () => {
      try {
        setScanningTypes(true);
        const res = await detectNumericTextColumns();
        if (res.success) {
          setSuspiciousColumns(res.suspicious_columns || []);
        }
      } catch (e) {
        // Silent fail — scan is optional
      } finally {
        setScanningTypes(false);
      }
    };
    scan();
  }, [columns, loading]); // Re-scan when columns change (after cleaning)

  const handleConvertType = async (columnName: string, targetType: string) => {
    const confirmMsg = `The column "${columnName}" is currently stored in TEXT format. Would you like to convert it to ${targetType.toUpperCase()}? Any non-numeric text values in this column will be set to NULL.`;
    if (!window.confirm(confirmMsg)) return;

    try {
      setCleaning(true);
      setStatusMessage(null);
      const data = await cleanConvertType(columnName, targetType);
      if (data.success) {
        setStatusMessage({ type: "success", text: data.message });
        onRefresh();
      } else {
        setStatusMessage({ type: "error", text: data.error || "Failed to convert column datatype." });
      }
    } catch (e: any) {
      setStatusMessage({ type: "error", text: e.message || "Failed to convert column datatype." });
    } finally {
      setCleaning(false);
    }
  };

  const handleExtractAndConvert = async (columnName: string) => {
    const confirmMsg = `"${columnName}" contains numbers mixed with text (e.g. "1234 USD"). \n\nThis will:\n1. Strip all non-numeric characters (currencies, units, symbols)\n2. Convert the column datatype to NUMERIC\n\nProceed?`;
    if (!window.confirm(confirmMsg)) return;
    try {
      setCleaning(true);
      setStatusMessage(null);
      const data = await cleanExtractAndConvert(columnName);
      if (data.success) {
        setStatusMessage({ type: "success", text: data.message });
        onRefresh(); // This triggers re-scan and re-render
      } else {
        setStatusMessage({ type: "error", text: data.error || "Failed to fix column." });
      }
    } catch (e: any) {
      setStatusMessage({ type: "error", text: e.message || "Failed to fix column." });
    } finally {
      setCleaning(false);
    }
  };
  const [strategy, setStrategy] = useState("mean");
  const [customValue, setCustomValue] = useState("");

  const handleRemoveDuplicates = async () => {
    try {
      setCleaning(true);
      setStatusMessage(null);
      const data = await cleanRemoveDuplicates();
      if (data.success) {
        setStatusMessage({
          type: "success",
          text: data.message
        });
        onRefresh();
      } else {
        setStatusMessage({
          type: "error",
          text: data.error || "Failed removing duplicate rows."
        });
      }
    } catch (e: any) {
      setStatusMessage({
        type: "error",
        text: e.message || "Failed removing duplicate rows."
      });
    } finally {
      setCleaning(false);
    }
  };

  const handleImpute = async () => {
    if (!selectedColumn) {
      alert("Please select a column to clean.");
      return;
    }
    try {
      setCleaning(true);
      setStatusMessage(null);
      const data = await cleanImpute(selectedColumn, strategy, customValue);
      if (data.success) {
        setStatusMessage({
          type: "success",
          text: data.message
        });
        setCustomValue("");
        onRefresh();
      } else {
        setStatusMessage({
          type: "error",
          text: data.error || "Failed executing imputation."
        });
      }
    } catch (e: any) {
      setStatusMessage({
        type: "error",
        text: e.message || "Failed executing imputation."
      });
    } finally {
      setCleaning(false);
    }
  };

  const isNumericType = (col: string) => {
    const type = (detectedTypes[col] || "").toLowerCase();
    return type === "numeric" || type === "int" || type === "float" || type === "decimal" || type === "double";
  };

  const [standardizeCol, setStandardizeCol] = useState("");
  const [standardizeOp, setStandardizeOp] = useState("trim");
  
  const handleStandardizeText = async () => {
    if (!standardizeCol) return;
    try {
      setCleaning(true);
      setStatusMessage(null);
      const data = await cleanStandardizeText(standardizeCol, standardizeOp);
      if (data.success) {
        setStatusMessage({ type: "success", text: data.message });
        onRefresh();
      } else {
        setStatusMessage({ type: "error", text: data.error || "Failed standardizing text." });
      }
    } catch (e: any) {
      setStatusMessage({ type: "error", text: e.message || "Failed standardizing text." });
    } finally {
      setCleaning(false);
    }
  };

  const [extractCol, setExtractCol] = useState("");
  
  const handleExtractNumbers = async () => {
    if (!extractCol) return;
    try {
      setCleaning(true);
      setStatusMessage(null);
      const data = await cleanExtractNumbers(extractCol);
      if (data.success) {
        setStatusMessage({ type: "success", text: data.message });
        onRefresh();
      } else {
        setStatusMessage({ type: "error", text: data.error || "Failed extracting numbers." });
      }
    } catch (e: any) {
      setStatusMessage({ type: "error", text: e.message || "Failed extracting numbers." });
    } finally {
      setCleaning(false);
    }
  };

  const [outlierCol, setOutlierCol] = useState("");
  const [lowerBound, setLowerBound] = useState(0.05);
  const [upperBound, setUpperBound] = useState(0.95);
  
  const handleCapOutliers = async () => {
    if (!outlierCol) return;
    try {
      setCleaning(true);
      setStatusMessage(null);
      const data = await cleanCapOutliers(outlierCol, lowerBound, upperBound);
      if (data.success) {
        setStatusMessage({ type: "success", text: data.message });
        onRefresh();
      } else {
        setStatusMessage({ type: "error", text: data.error || "Failed capping outliers." });
      }
    } catch (e: any) {
      setStatusMessage({ type: "error", text: e.message || "Failed capping outliers." });
    } finally {
      setCleaning(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-[#111113] border border-white/[0.06] rounded-2xl p-5 shadow-2xl shadow-black/10">
        <div className="flex items-center gap-3">
          <div className="bg-indigo-500/10 p-2.5 rounded-xl text-indigo-400 border border-indigo-500/20">
            <Wand2 size={20} className="text-indigo-450" />
          </div>
          <div>
            <h2 className="text-base font-bold text-white">AI Data Cleaning & Preprocessing Suite</h2>
            <p className="text-zinc-400 text-[10px] mt-0.5 font-medium">
              Preprocess and repair column missing cells, values, and de-duplicate records directly inside MySQL.
            </p>
          </div>
        </div>
      </div>

      {/* Status Notifications */}
      {statusMessage && (
        <div className={`p-4 border rounded-xl flex items-start gap-3 text-xs font-semibold animate-fade-in ${
          statusMessage.type === "success" 
            ? "bg-emerald-500/10 border-emerald-500/20 text-emerald-400" 
            : "bg-red-500/10 border-red-500/20 text-red-400"
        }`}>
          {statusMessage.type === "success" ? (
            <CheckCircle size={16} className="text-emerald-400 mt-0.5 shrink-0" />
          ) : (
            <AlertTriangle size={16} className="text-red-400 mt-0.5 shrink-0" />
          )}
          <div>{statusMessage.text}</div>
        </div>
      )}

      {/* Smart Numeric Detection Banner */}
      {!scanningTypes && suspiciousColumns.length > 0 && (
        <div className="bg-amber-500/[0.06] border border-amber-500/30 rounded-2xl p-5 space-y-3">
          <div className="flex items-center gap-2">
            <div className="bg-amber-500/10 p-2 rounded-lg border border-amber-500/20">
              <Zap size={15} className="text-amber-400" />
            </div>
            <div>
              <h3 className="text-xs font-bold text-amber-300">Smart Detection: Numeric Values in Text Columns</h3>
              <p className="text-[10px] text-amber-500/80 mt-0.5">The following columns contain numeric-looking data stored as text. Fix them in one click to enable math, stats, and proper querying.</p>
            </div>
          </div>
          <div className="space-y-2">
            {suspiciousColumns.map((item) => (
              <div key={item.column} className="flex items-center justify-between bg-[#111113] border border-white/[0.06] rounded-xl px-4 py-2.5">
                <div className="flex items-center gap-3">
                  <span className="font-bold text-xs text-white">{item.column}</span>
                  <span className="text-[9px] text-zinc-500 font-mono bg-white/[0.04] px-2 py-0.5 rounded">
                    {item.sample_values.slice(0, 3).join(" · ")}
                  </span>
                  <span className="text-[9px] font-bold text-amber-400">{Math.round(item.numeric_ratio * 100)}% numeric</span>
                </div>
                <button
                  onClick={() => handleExtractAndConvert(item.column)}
                  disabled={cleaning}
                  className="flex items-center gap-1.5 text-[10px] font-bold text-white bg-amber-500/20 hover:bg-amber-500/30 border border-amber-500/30 px-3 py-1.5 rounded-lg transition cursor-pointer disabled:opacity-50"
                >
                  <Zap size={10} />
                  Fix & Convert to Numeric
                </button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Cleaner Workspace grid */}
      <div className="grid md:grid-cols-3 gap-6">
        {/* De-duplication Card */}
        <div className="bg-[#FFFDFC] border border-[#E8DED3] rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="text-xs font-bold text-[#241C20] flex items-center gap-2">
            <Trash2 className="text-[#5A2F59]" size={15} />
            <span>Deduplicate Dataset</span>
          </h3>
          <p className="text-[10px] text-[#6F6A67] leading-relaxed font-medium">
            Copies all distinct rows into a temporary storage workspace, flushes the original table, and repopulates the clean records.
          </p>
          <button
            onClick={handleRemoveDuplicates}
            disabled={cleaning || loading}
            className="w-full flex items-center justify-center gap-2 bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] font-bold text-xs py-2.5 px-4 rounded-xl transition shadow-sm hover:shadow active:scale-98 cursor-pointer disabled:opacity-50"
          >
            {cleaning ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Wand2 size={13} />
            )}
            <span>Remove Duplicate Rows</span>
          </button>
        </div>

        {/* Column Imputation Card */}
        <div className="md:col-span-2 bg-[#111113] border border-white/[0.06] rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="text-xs font-bold text-white flex items-center gap-2">
            <Sparkles className="text-indigo-400" size={15} />
            <span>Missing Cells Imputer (Repair Nulls)</span>
          </h3>
          <p className="text-[10px] text-zinc-400 leading-relaxed font-semibold">
            Detects empty string and NULL cells in a selected column, calculating replacements based on statistical means, medians, modes, or custom constants.
          </p>

          <div className="grid sm:grid-cols-2 gap-4">
            {/* Column select */}
            <div className="space-y-1">
              <label className="text-[9px] uppercase tracking-wider font-extrabold text-zinc-500 block">Select Column</label>
              <select
                value={selectedColumn}
                onChange={(e) => {
                  setSelectedColumn(e.target.value);
                  // Default to mode if non-numeric
                  if (e.target.value && !isNumericType(e.target.value)) {
                    setStrategy("mode");
                  } else {
                    setStrategy("mean");
                  }
                }}
                className="w-full bg-[#18181B] border border-white/[0.08] rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 text-zinc-300 font-semibold cursor-pointer"
              >
                <option value="">-- Choose Column --</option>
                {columns.map((col) => (
                  <option key={col} value={col}>
                    {col} ({detectedTypes[col] || "text"}) - {columnMissing[col] || 0} nulls
                  </option>
                ))}
              </select>
            </div>

            {/* Imputation Strategy */}
            <div className="space-y-1">
              <label className="text-[9px] uppercase tracking-wider font-extrabold text-zinc-500 block">Cleaning Strategy</label>
              <select
                value={strategy}
                onChange={(e) => setStrategy(e.target.value)}
                disabled={!selectedColumn}
                className="w-full bg-[#18181B] border border-white/[0.08] rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 text-zinc-300 font-semibold cursor-pointer disabled:opacity-50"
              >
                {selectedColumn && isNumericType(selectedColumn) && (
                  <>
                    <option value="mean">Mean (Fill with Average)</option>
                    <option value="median">Median (Fill with Middle Value)</option>
                  </>
                )}
                <option value="mode">Mode (Fill with Most Frequent)</option>
                <option value="custom">Custom (Specify value below)</option>
                <option value="drop">Drop Rows (Delete rows where column is null)</option>
              </select>
            </div>
          </div>

          {/* Custom value input */}
          {strategy === "custom" && (
            <div className="space-y-1 animate-fade-in">
              <label className="text-[9px] uppercase tracking-wider font-extrabold text-zinc-500 block">Custom Replacement Value</label>
              <input
                type="text"
                placeholder="Enter custom replacement text or number..."
                value={customValue}
                onChange={(e) => setCustomValue(e.target.value)}
                className="w-full bg-[#18181B] border border-white/[0.08] rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 text-zinc-300 font-medium"
              />
            </div>
          )}

          {/* Numeric/Sales Columns Warning */}
          {selectedColumn && (isNumericType(selectedColumn) || selectedColumn.toLowerCase().includes("sale") || selectedColumn.toLowerCase().includes("price") || selectedColumn.toLowerCase().includes("quantity")) && (strategy === "custom" || strategy === "mode" || strategy === "mean" || strategy === "median") && (
            <div className="bg-amber-500/[0.06] border border-amber-500/20 rounded-xl p-3.5 flex items-start gap-2.5 text-[10px] text-amber-300 font-semibold animate-fade-in">
              <AlertTriangle size={15} className="text-amber-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-bold text-amber-400 block mb-0.5">⚠️ Data Integrity Suggestion</span>
                You are applying a uniform value (or column statistic) to a transaction metric ({selectedColumn}). 
                Because sales and quantities differ per transaction, overwriting all empty cells with the same constant might skew your data.
                To input different, unique values for each cell, use the <strong>Data Table Preview</strong> tab and double-click individual cells to edit them row-by-row.
              </div>
            </div>
          )}

          <button
            onClick={handleImpute}
            disabled={cleaning || loading || !selectedColumn}
            className="flex items-center justify-center gap-2 bg-[#18181B] border border-white/[0.08] hover:border-indigo-500 hover:bg-indigo-500/10 text-white font-bold text-xs py-2.5 px-6 rounded-xl transition shadow-sm active:scale-98 cursor-pointer disabled:opacity-50 block ml-auto"
          >
            {cleaning ? (
              <Loader2 size={13} className="animate-spin" />
            ) : (
              <Sparkles size={13} className="text-indigo-400" />
            )}
            <span>Apply Repair</span>
          </button>
        </div>
      </div>

      <div className="grid md:grid-cols-3 gap-6">
        {/* Text Standardization Card */}
        <div className="bg-[#111113] border border-white/[0.06] rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="text-xs font-bold text-white flex items-center gap-2">
            <Type className="text-indigo-400" size={15} />
            <span>Text Standardization</span>
          </h3>
          <p className="text-[10px] text-zinc-400 leading-relaxed font-semibold">
            Clean messy strings by trimming whitespace or standardizing to upper/lower casing.
          </p>
          <div className="space-y-2">
            <select
              value={standardizeCol}
              onChange={(e) => setStandardizeCol(e.target.value)}
              className="w-full bg-[#18181B] border border-white/[0.08] rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 text-zinc-300 font-semibold cursor-pointer"
            >
              <option value="">-- Choose Column --</option>
              {columns.map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
            <select
              value={standardizeOp}
              onChange={(e) => setStandardizeOp(e.target.value)}
              className="w-full bg-[#18181B] border border-white/[0.08] rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 text-zinc-300 font-semibold cursor-pointer"
            >
              <option value="trim">Trim Whitespace</option>
              <option value="lower">Lowercase</option>
              <option value="upper">Uppercase</option>
            </select>
            <button
              onClick={handleStandardizeText}
              disabled={cleaning || loading || !standardizeCol}
              className="w-full flex items-center justify-center gap-2 bg-[#18181B] border border-white/[0.08] hover:border-indigo-500 hover:bg-indigo-500/10 text-white font-bold text-xs py-2 px-4 rounded-xl transition shadow-sm active:scale-98 cursor-pointer disabled:opacity-50"
            >
              <span>Standardize</span>
            </button>
          </div>
        </div>

        {/* Number Extraction Card */}
        <div className="bg-[#111113] border border-white/[0.06] rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="text-xs font-bold text-white flex items-center gap-2">
            <Scissors className="text-indigo-400" size={15} />
            <span>Smart Number Extraction</span>
          </h3>
          <p className="text-[10px] text-zinc-400 leading-relaxed font-semibold">
            Extracts numeric digits from messy text strings (e.g. currencies, strings with text).
          </p>
          <div className="space-y-2">
            <select
              value={extractCol}
              onChange={(e) => setExtractCol(e.target.value)}
              className="w-full bg-[#18181B] border border-white/[0.08] rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 text-zinc-300 font-semibold cursor-pointer"
            >
              <option value="">-- Choose Column --</option>
              {columns.map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
            <div className="text-[9px] text-emerald-400 bg-emerald-500/[0.06] px-2.5 py-1.5 rounded-lg border border-emerald-500/20 font-semibold mt-2">
              Removes all letters and symbols except digits, dots, and minus signs.
            </div>
            <button
              onClick={handleExtractNumbers}
              disabled={cleaning || loading || !extractCol}
              className="w-full mt-2 flex items-center justify-center gap-2 bg-[#18181B] border border-white/[0.08] hover:border-indigo-500 hover:bg-indigo-500/10 text-white font-bold text-xs py-2 px-4 rounded-xl transition shadow-sm active:scale-98 cursor-pointer disabled:opacity-50"
            >
              <span>Extract Numbers</span>
            </button>
          </div>
        </div>

        {/* Outlier Capping Card */}
        <div className="bg-[#111113] border border-white/[0.06] rounded-2xl p-5 shadow-sm space-y-4">
          <h3 className="text-xs font-bold text-white flex items-center gap-2">
            <Activity className="text-indigo-400" size={15} />
            <span>Outlier Capping (Winsorization)</span>
          </h3>
          <p className="text-[10px] text-zinc-400 leading-relaxed font-semibold">
            Caps extreme numerical outliers to percentiles boundaries.
          </p>
          <div className="space-y-2">
            <select
              value={outlierCol}
              onChange={(e) => setOutlierCol(e.target.value)}
              className="w-full bg-[#18181B] border border-white/[0.08] rounded-xl px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 text-zinc-300 font-semibold cursor-pointer"
            >
              <option value="">-- Numeric Column --</option>
              {columns.filter(c => isNumericType(c)).map((col) => (
                <option key={col} value={col}>{col}</option>
              ))}
            </select>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[8px] uppercase tracking-wider font-extrabold text-zinc-500 block mb-1">Lower Limit</label>
                <input
                  type="number"
                  step="0.01"
                  min="0"
                  max="0.5"
                  value={lowerBound}
                  onChange={(e) => setLowerBound(parseFloat(e.target.value))}
                  className="w-full bg-[#18181B] border border-white/[0.08] rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-indigo-500 text-zinc-300"
                />
              </div>
              <div>
                <label className="text-[8px] uppercase tracking-wider font-extrabold text-zinc-500 block mb-1">Upper Limit</label>
                <input
                  type="number"
                  step="0.01"
                  min="0.5"
                  max="1"
                  value={upperBound}
                  onChange={(e) => setUpperBound(parseFloat(e.target.value))}
                  className="w-full bg-[#18181B] border border-white/[0.08] rounded-lg px-2 py-1.5 text-xs focus:outline-none focus:border-indigo-500 text-zinc-300"
                />
              </div>
            </div>
            <button
              onClick={handleCapOutliers}
              disabled={cleaning || loading || !outlierCol}
              className="w-full mt-2 flex items-center justify-center gap-2 bg-[#18181B] border border-white/[0.08] hover:border-indigo-500 hover:bg-indigo-500/10 text-white font-bold text-xs py-2 px-4 rounded-xl transition shadow-sm active:scale-98 cursor-pointer disabled:opacity-50"
            >
              <span>Cap Outliers</span>
            </button>
          </div>
        </div>
      </div>

      {/* Dataset Audit details Table */}
      <div className="bg-[#111113] border border-white/[0.06] rounded-2xl p-5 shadow-2xl shadow-black/10 space-y-4">
        <h3 className="text-xs font-bold text-white flex items-center gap-2">
          <Database className="text-indigo-400" size={15} />
          <span>Column Schema Health Audit</span>
        </h3>
        <div className="overflow-x-auto border border-white/[0.06] rounded-xl max-h-[300px]">
          <table className="min-w-full border-collapse text-left text-xs text-zinc-300">
            <thead className="bg-[#0D0D0F] sticky top-0 border-b border-white/[0.06] z-10 font-bold text-[9px] uppercase text-zinc-500 tracking-wider">
              <tr>
                <th className="px-4 py-3.5">Column Name</th>
                <th className="px-4 py-3.5">Detected Type</th>
                <th className="px-4 py-3.5 text-center">Missing Cells</th>
                <th className="px-4 py-3.5">Health Status</th>
                <th className="px-4 py-3.5">Statistics</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] bg-[#111113] font-semibold">
              {columns.map((col) => {
                const nullsCount = columnMissing[col] || 0;
                const isHealthy = nullsCount === 0;
                const stats = columnStats?.[col];
                return (
                  <tr key={col} className="hover:bg-white/[0.02] transition">
                    <td className="px-4 py-3 font-bold text-zinc-200">{col}</td>
                    <td className="px-4 py-3 font-mono text-[10px] text-zinc-500">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${
                          (detectedTypes[col] || "text") === "numeric"
                            ? "text-sky-400 border-sky-500/20 bg-sky-500/10"
                            : (detectedTypes[col] || "text") === "date"
                            ? "text-violet-400 border-violet-500/20 bg-violet-500/10"
                            : "text-zinc-400 border-white/[0.08] bg-white/[0.03]"
                        }`}>{detectedTypes[col] || "text"}</span>
                        {/* Show Fix button for columns detected as suspicious */}
                        {suspiciousColumns.find(s => s.column === col) && (
                          <button
                            onClick={() => handleExtractAndConvert(col)}
                            disabled={cleaning || loading}
                            className="text-[9px] font-bold text-amber-400 hover:text-amber-300 bg-amber-500/10 hover:bg-amber-500/20 px-2 py-0.5 rounded border border-amber-500/20 cursor-pointer transition flex items-center gap-1"
                          >
                            <Zap size={9} /> Fix → Numeric
                          </button>
                        )}
                        {/* Show plain convert for confirmed text columns by name */}
                        {!suspiciousColumns.find(s => s.column === col) && (detectedTypes[col] || "text") === "text" && (
                          <button
                            onClick={() => handleConvertType(col, "numeric")}
                            disabled={cleaning || loading}
                            className="text-[9px] font-bold text-zinc-500 hover:text-indigo-400 hover:bg-indigo-500/10 px-1.5 py-0.5 rounded border border-white/[0.08] hover:border-indigo-500/20 cursor-pointer transition"
                          >
                            → Numeric
                          </button>
                        )}
                      </div>
                    </td>
                    <td className="px-4 py-3 text-center text-zinc-200">{nullsCount}</td>
                    <td className="px-4 py-3">
                      {isHealthy ? (
                        <span className="inline-flex items-center gap-1 text-[10px] text-emerald-400 font-bold bg-emerald-500/[0.06] px-2 py-0.5 border border-emerald-500/20 rounded-full">
                          <CheckCircle size={10} />
                          <span>100% Clean</span>
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 text-[10px] text-amber-400 font-bold bg-amber-500/[0.06] px-2 py-0.5 border border-amber-500/20 rounded-full">
                          <AlertTriangle size={10} />
                          <span>Needs Review</span>
                        </span>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      {stats ? (
                        <div className="flex flex-wrap gap-2 text-[9px] font-mono text-zinc-400">
                          <span className="bg-white/[0.03] border border-white/[0.05] px-1.5 py-0.5 rounded">Mean: {stats.mean?.toFixed(2)}</span>
                          <span className="bg-white/[0.03] border border-white/[0.05] px-1.5 py-0.5 rounded">Med: {stats.median?.toFixed(2)}</span>
                          <span className="bg-white/[0.03] border border-white/[0.05] px-1.5 py-0.5 rounded">Min: {stats.min?.toFixed(2)}</span>
                          <span className="bg-white/[0.03] border border-white/[0.05] px-1.5 py-0.5 rounded">Max: {stats.max?.toFixed(2)}</span>
                        </div>
                      ) : (
                        <span className="text-[9px] text-zinc-600 font-medium italic">N/A (Non-numeric)</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
