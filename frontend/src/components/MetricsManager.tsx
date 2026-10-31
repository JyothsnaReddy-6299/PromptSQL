import { useState, useEffect } from "react";
import { 
  Target, 
  Plus, 
  Trash2, 
  Edit3, 
  Play, 
  Check, 
  AlertCircle, 
  Loader2, 
  Sparkles, 
  Database, 
  Tag,
  X
} from "lucide-react";
import { getMetrics, createMetric, updateMetric, deleteMetric, testMetric, getDatasets } from "../services/api";

interface Metric {
  id: number;
  name: string;
  description: string;
  approved_aliases: string[];
  source_dataset: string;
  supported_aggregation: string;
  relevant_columns: string[];
  expression: string;
  optional_filters: any[];
  currency_unit: string;
  version: number;
  created_at: string;
  updated_at: string;
}

export default function MetricsManager() {
  const [metrics, setMetrics] = useState<Metric[]>([]);
  const [datasets, setDatasets] = useState<string[]>([]);
  const [selectedDataset, setSelectedDataset] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // Modal states
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingMetric, setEditingMetric] = useState<Metric | null>(null);

  // Form states
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formDataset, setFormDataset] = useState("");
  const [formExpression, setFormExpression] = useState("");
  const [formAggregation, setFormAggregation] = useState("SUM");
  const [formAliases, setFormAliases] = useState("");
  const [formUnit, setFormUnit] = useState("");

  // Testing states
  const [testing, setTesting] = useState(false);
  const [testResult, setTestResult] = useState<any | null>(null);
  const [testError, setTestError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  // Active dataset from session
  useEffect(() => {
    try {
      const stored = JSON.parse(sessionStorage.getItem("dataset") || "{}");
      if (stored && stored.table_name) {
        setSelectedDataset(stored.table_name);
        setFormDataset(stored.table_name);
      }
    } catch (e) {}

    getDatasets().then((res) => {
      if (res.success && res.datasets) {
        setDatasets(res.datasets);
        if (!selectedDataset && res.datasets.length > 0) {
          setSelectedDataset(res.datasets[0]);
          setFormDataset(res.datasets[0]);
        }
      }
    });

    loadMetrics();
  }, []);

  const loadMetrics = async (datasetToFilter?: string) => {
    try {
      setLoading(true);
      setError(null);
      const res = await getMetrics(datasetToFilter !== undefined ? datasetToFilter : selectedDataset);
      if (res.success) {
        setMetrics(res.metrics || []);
      }
    } catch (err: any) {
      setError(err.message || "Failed to load metrics");
    } finally {
      setLoading(false);
    }
  };

  const handleOpenModal = (metric?: Metric) => {
    if (metric) {
      setEditingMetric(metric);
      setFormName(metric.name);
      setFormDescription(metric.description || "");
      setFormDataset(metric.source_dataset);
      setFormExpression(metric.expression);
      setFormAggregation(metric.supported_aggregation);
      setFormAliases((metric.approved_aliases || []).join(", "));
      setFormUnit(metric.currency_unit || "");
    } else {
      setEditingMetric(null);
      setFormName("");
      setFormDescription("");
      setFormDataset(selectedDataset || (datasets.length > 0 ? datasets[0] : ""));
      setFormExpression("");
      setFormAggregation("SUM");
      setFormAliases("");
      setFormUnit("USD");
    }
    setTestResult(null);
    setTestError(null);
    setIsModalOpen(true);
  };

  const handleTestExpression = async () => {
    if (!formExpression.trim() || !formDataset) {
      setTestError("Please enter an expression and select a source dataset.");
      return;
    }
    try {
      setTesting(true);
      setTestError(null);
      setTestResult(null);
      const res = await testMetric({
        source_dataset: formDataset,
        expression: formExpression.trim(),
        supported_aggregation: formAggregation
      });
      if (res.success) {
        setTestResult(res);
      } else {
        setTestError(res.error || "Expression test failed");
      }
    } catch (err: any) {
      setTestError(err.message || "Failed testing expression");
    } finally {
      setTesting(false);
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!formName.trim() || !formExpression.trim() || !formDataset) {
      setTestError("Name, expression, and dataset are required.");
      return;
    }

    const aliases = formAliases
      .split(",")
      .map((a) => a.trim())
      .filter((a) => a.length > 0);

    try {
      setSaving(true);
      setTestError(null);

      const payload = {
        name: formName.trim(),
        description: formDescription.trim(),
        source_dataset: formDataset,
        expression: formExpression.trim(),
        supported_aggregation: formAggregation,
        approved_aliases: aliases,
        currency_unit: formUnit.trim(),
      };

      if (editingMetric) {
        await updateMetric(editingMetric.id, payload);
      } else {
        await createMetric(payload);
      }

      setIsModalOpen(false);
      loadMetrics();
    } catch (err: any) {
      setTestError(err.message || "Failed saving metric");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!window.confirm("Are you sure you want to delete this metric definition?")) return;
    try {
      await deleteMetric(id);
      loadMetrics();
    } catch (err: any) {
      alert(err.message || "Failed to delete metric");
    }
  };

  return (
    <div className="p-6 max-w-7xl mx-auto space-y-6 text-left">
      {/* Page Header */}
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 bg-[#FFFDFC] border-2 border-[#E8DED3] p-6 rounded-3xl shadow-sm">
        <div>
          <div className="flex items-center gap-2 text-[#5A2F59] font-bold text-xs uppercase tracking-wider mb-1">
            <Target className="w-4 h-4 text-[#BDA37A]" />
            <span>Semantic Layer & Governance</span>
          </div>
          <h1 className="text-2xl font-black text-[#241C20] tracking-tight">Business Metric Registry</h1>
          <p className="text-xs text-[#6F6A67] mt-1 max-w-xl">
            Define reusable, validated business metrics (e.g., Revenue, AOV, Volume). PromptSQL uses these trusted definitions to resolve ambiguous questions deterministically.
          </p>
        </div>

        <button
          onClick={() => handleOpenModal()}
          className="flex items-center gap-2 bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] text-xs font-bold px-4 py-2.5 rounded-xl shadow-md shadow-[#5A2F59]/20 transition cursor-pointer shrink-0"
        >
          <Plus className="w-4 h-4" />
          <span>Define New Metric</span>
        </button>
      </div>

      {/* Dataset Filter Toolbar */}
      <div className="flex items-center gap-3 bg-[#FFFDFC] border border-[#E8DED3] p-3 rounded-2xl">
        <Database className="w-4 h-4 text-[#BDA37A] shrink-0 ml-2" />
        <span className="text-xs font-bold text-[#6F6A67]">Dataset Scope:</span>
        <select
          value={selectedDataset}
          onChange={(e) => {
            setSelectedDataset(e.target.value);
            loadMetrics(e.target.value);
          }}
          className="text-xs bg-[#F7F2EC] border border-[#E8DED3] text-[#241C20] rounded-xl px-3 py-1.5 focus:outline-none font-medium cursor-pointer"
        >
          <option value="">All Datasets</option>
          {datasets.map((d) => (
            <option key={d} value={d}>
              {d.split("_usr_")[0]}
            </option>
          ))}
        </select>
        <div className="ml-auto text-[11px] font-semibold text-[#8C827A]">
          {metrics.length} metric{metrics.length === 1 ? "" : "s"} registered
        </div>
      </div>

      {/* Metric Cards Grid */}
      {loading ? (
        <div className="p-12 flex flex-col items-center justify-center text-center gap-3">
          <Loader2 className="w-8 h-8 text-[#5A2F59] animate-spin" />
          <p className="text-xs text-[#6F6A67] font-medium">Loading workspace metrics...</p>
        </div>
      ) : error ? (
        <div className="p-4 bg-[#D95D39]/10 border border-[#D95D39]/30 rounded-2xl text-xs text-[#D95D39] flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          <span>{error}</span>
        </div>
      ) : metrics.length === 0 ? (
        <div className="p-12 text-center bg-[#FFFDFC] border-2 border-[#E8DED3] border-dashed rounded-3xl space-y-3">
          <div className="w-12 h-12 bg-[#5A2F59]/10 text-[#5A2F59] rounded-2xl flex items-center justify-center mx-auto">
            <Sparkles className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-bold text-[#241C20]">No business metrics defined yet</h3>
          <p className="text-xs text-[#6F6A67] max-w-md mx-auto">
            Create definitions like "Revenue" or "Order Quantity". When users ask natural language questions like "Highest sales", PromptSQL resolves them using these approved calculations.
          </p>
          <button
            onClick={() => handleOpenModal()}
            className="inline-flex items-center gap-1.5 bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] text-xs font-bold px-4 py-2 rounded-xl transition cursor-pointer mt-2"
          >
            <Plus className="w-4 h-4" />
            <span>Create First Metric</span>
          </button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {metrics.map((m) => (
            <div
              key={m.id}
              className="bg-[#FFFDFC] border-2 border-[#E8DED3] hover:border-[#5A2F59]/30 p-5 rounded-3xl shadow-sm hover:shadow-md transition-all flex flex-col justify-between gap-4"
            >
              <div>
                {/* Header row */}
                <div className="flex items-start justify-between gap-2">
                  <div className="space-y-0.5">
                    <div className="flex items-center gap-2">
                      <h3 className="font-bold text-sm text-[#241C20]">{m.name}</h3>
                      <span className="text-[9px] bg-[#5A2F59]/10 text-[#5A2F59] font-black px-1.5 py-0.5 rounded-md">
                        v{m.version}
                      </span>
                    </div>
                    <span className="text-[10px] text-[#8C827A] font-medium flex items-center gap-1">
                      <Database className="w-3 h-3 text-[#BDA37A]" />
                      {m.source_dataset.split("_usr_")[0]}
                    </span>
                  </div>

                  <div className="flex items-center gap-1">
                    <span className="text-[10px] bg-[#3E8E5B]/10 text-[#3E8E5B] border border-[#3E8E5B]/20 font-bold px-2 py-0.5 rounded-lg">
                      {m.supported_aggregation}
                    </span>
                    {m.currency_unit && (
                      <span className="text-[10px] bg-[#BDA37A]/15 text-[#5A2F59] font-bold px-2 py-0.5 rounded-lg">
                        {m.currency_unit}
                      </span>
                    )}
                  </div>
                </div>

                {/* Description */}
                {m.description && (
                  <p className="text-xs text-[#6F6A67] mt-2 line-clamp-2 leading-relaxed">
                    {m.description}
                  </p>
                )}

                {/* Expression Formula */}
                <div className="mt-3 bg-[#F7F2EC] border border-[#E8DED3] p-2.5 rounded-xl font-mono text-[11px] text-[#5A2F59] font-bold">
                  {m.supported_aggregation}({m.expression})
                </div>

                {/* Approved Aliases */}
                {m.approved_aliases && m.approved_aliases.length > 0 && (
                  <div className="mt-3 flex flex-wrap items-center gap-1.5">
                    <span className="text-[10px] text-[#8C827A] font-bold flex items-center gap-1">
                      <Tag className="w-2.5 h-2.5" /> Aliases:
                    </span>
                    {m.approved_aliases.map((alias) => (
                      <span
                        key={alias}
                        className="text-[9.5px] bg-[#FFFDFC] border border-[#E8DED3] text-[#241C20] px-1.5 py-0.5 rounded-md font-medium"
                      >
                        {alias}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              {/* Bottom Actions */}
              <div className="pt-3 border-t border-[#E8DED3] flex items-center justify-between text-xs">
                <span className="text-[10px] text-[#B0A79E]">
                  Updated {m.updated_at ? new Date(m.updated_at).toLocaleDateString() : ""}
                </span>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => handleOpenModal(m)}
                    className="p-1.5 text-[#6F6A67] hover:text-[#5A2F59] hover:bg-[#5A2F59]/5 rounded-lg transition cursor-pointer"
                    title="Edit metric"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                  </button>
                  <button
                    onClick={() => handleDelete(m.id)}
                    className="p-1.5 text-[#6F6A67] hover:text-[#D95D39] hover:bg-[#D95D39]/10 rounded-lg transition cursor-pointer"
                    title="Delete metric"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Define / Edit Modal */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs">
          <div className="bg-[#FFFDFC] border-2 border-[#E8DED3] rounded-3xl max-w-lg w-full p-6 shadow-2xl space-y-4 max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-[#E8DED3] pb-3">
              <div className="flex items-center gap-2">
                <div className="p-2 bg-[#5A2F59] text-[#BDA37A] rounded-xl">
                  <Target className="w-4 h-4" />
                </div>
                <h3 className="font-bold text-sm text-[#241C20]">
                  {editingMetric ? "Edit Business Metric" : "Define New Business Metric"}
                </h3>
              </div>
              <button
                onClick={() => setIsModalOpen(false)}
                className="p-1 text-[#6F6A67] hover:text-[#241C20] rounded-lg cursor-pointer"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <form onSubmit={handleSave} className="space-y-3.5 text-xs">
              {/* Metric Name */}
              <div>
                <label className="block text-[11px] font-bold text-[#6F6A67] uppercase tracking-wider mb-1">
                  Metric Name *
                </label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Total Revenue, Order Volume, AOV"
                  value={formName}
                  onChange={(e) => setFormName(e.target.value)}
                  className="w-full px-3 py-2 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl focus:outline-none focus:border-[#5A2F59] font-medium text-[#241C20]"
                />
              </div>

              {/* Source Dataset */}
              <div>
                <label className="block text-[11px] font-bold text-[#6F6A67] uppercase tracking-wider mb-1">
                  Source Dataset *
                </label>
                <select
                  required
                  value={formDataset}
                  onChange={(e) => setFormDataset(e.target.value)}
                  className="w-full px-3 py-2 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl focus:outline-none focus:border-[#5A2F59] font-medium text-[#241C20] cursor-pointer"
                >
                  {datasets.map((d) => (
                    <option key={d} value={d}>
                      {d.split("_usr_")[0]}
                    </option>
                  ))}
                </select>
              </div>

              {/* Aggregation & Unit row */}
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-[11px] font-bold text-[#6F6A67] uppercase tracking-wider mb-1">
                    Aggregation *
                  </label>
                  <select
                    value={formAggregation}
                    onChange={(e) => setFormAggregation(e.target.value)}
                    className="w-full px-3 py-2 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl focus:outline-none focus:border-[#5A2F59] font-medium text-[#241C20] cursor-pointer"
                  >
                    <option value="SUM">SUM</option>
                    <option value="AVG">AVG (Average)</option>
                    <option value="COUNT">COUNT</option>
                    <option value="COUNT_DISTINCT">COUNT DISTINCT</option>
                    <option value="MIN">MIN</option>
                    <option value="MAX">MAX</option>
                  </select>
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-[#6F6A67] uppercase tracking-wider mb-1">
                    Currency / Unit
                  </label>
                  <input
                    type="text"
                    placeholder="e.g. USD, $, units, orders"
                    value={formUnit}
                    onChange={(e) => setFormUnit(e.target.value)}
                    className="w-full px-3 py-2 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl focus:outline-none focus:border-[#5A2F59] font-medium text-[#241C20]"
                  />
                </div>
              </div>

              {/* Expression with Test Button */}
              <div>
                <div className="flex items-center justify-between mb-1">
                  <label className="text-[11px] font-bold text-[#6F6A67] uppercase tracking-wider">
                    Calculation Expression *
                  </label>
                  <span className="text-[10px] text-[#8C827A]">Safe arithmetic (+, -, *, /)</span>
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    required
                    placeholder="e.g. Total_Sales or Unit_Price * Quantity_Ordered"
                    value={formExpression}
                    onChange={(e) => setFormExpression(e.target.value)}
                    className="w-full px-3 py-2 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl font-mono text-[11px] focus:outline-none focus:border-[#5A2F59] text-[#241C20]"
                  />
                  <button
                    type="button"
                    onClick={handleTestExpression}
                    disabled={testing || !formExpression.trim()}
                    className="bg-[#5A2F59]/10 hover:bg-[#5A2F59]/20 text-[#5A2F59] font-bold px-3 py-2 rounded-xl transition flex items-center gap-1 cursor-pointer shrink-0 disabled:opacity-50"
                  >
                    {testing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Play className="w-3.5 h-3.5" />}
                    <span>Test</span>
                  </button>
                </div>
              </div>

              {/* Test Result / Error Feedback */}
              {testResult && (
                <div className="p-3 bg-[#3E8E5B]/10 border border-[#3E8E5B]/30 rounded-xl space-y-1">
                  <div className="flex items-center gap-1.5 text-[#3E8E5B] font-bold text-[11px]">
                    <Check className="w-3.5 h-3.5" />
                    <span>Expression validated successfully!</span>
                  </div>
                  <div className="text-[10.5px] font-mono text-[#241C20]">
                    SQL: <code>{testResult.compiled_sql}</code>
                  </div>
                  {testResult.sample_value !== undefined && (
                    <div className="text-[10.5px] text-[#6F6A67]">
                      Sample aggregate output: <strong>{String(testResult.sample_value)}</strong>
                    </div>
                  )}
                </div>
              )}

              {testError && (
                <div className="p-3 bg-[#D95D39]/10 border border-[#D95D39]/30 rounded-xl text-[11px] text-[#D95D39] flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 shrink-0" />
                  <span>{testError}</span>
                </div>
              )}

              {/* Approved Aliases */}
              <div>
                <label className="block text-[11px] font-bold text-[#6F6A67] uppercase tracking-wider mb-1">
                  Approved Aliases (Comma-separated)
                </label>
                <input
                  type="text"
                  placeholder="e.g. sales, turnover, monetary sales, income"
                  value={formAliases}
                  onChange={(e) => setFormAliases(e.target.value)}
                  className="w-full px-3 py-2 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl focus:outline-none focus:border-[#5A2F59] font-medium text-[#241C20]"
                />
              </div>

              {/* Description */}
              <div>
                <label className="block text-[11px] font-bold text-[#6F6A67] uppercase tracking-wider mb-1">
                  Description
                </label>
                <textarea
                  rows={2}
                  placeholder="Explain how this metric is defined and when to use it..."
                  value={formDescription}
                  onChange={(e) => setFormDescription(e.target.value)}
                  className="w-full px-3 py-2 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl focus:outline-none focus:border-[#5A2F59] font-medium text-[#241C20]"
                />
              </div>

              {/* Modal Buttons */}
              <div className="pt-3 border-t border-[#E8DED3] flex justify-end gap-2">
                <button
                  type="button"
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-2 border border-[#E8DED3] text-[#6F6A67] hover:bg-[#F7F2EC] rounded-xl font-bold cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={saving}
                  className="px-4 py-2 bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] rounded-xl font-bold flex items-center gap-1.5 cursor-pointer shadow-md shadow-[#5A2F59]/20 disabled:opacity-50"
                >
                  {saving && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>{editingMetric ? "Update Metric" : "Save Metric"}</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
