import { useState, useEffect } from "react";
import {
  Sparkles,
  AlertTriangle,
  Search,
  RefreshCw,
  FolderHeart,
  Code2,
  Table,
  X,
  Copy,
  Check,
  ChevronDown,
  ChevronUp,
  Layers,
  DollarSign,
  ShoppingCart,
  TrendingUp,
  Award,
  Package,
  Users,
  GraduationCap,
  Trophy,
  AlertCircle,
  CheckCircle,
  BookOpen,
  Briefcase,
  Building,
  MapPin,
  BarChart3,
  PieChart,
  Filter,
  RotateCcw,
  ArrowUpRight,
  ArrowDownRight,
} from "lucide-react";
import { getDatasetInsights, createReport } from "../services/api";

interface Props {
  fileName?: string;
  onInvestigate?: (question: string, suggestedFollowups?: string[]) => void;
  onRefresh?: () => void;
}

export default function AIInsightsWorkspace({
  fileName = "",
  onInvestigate,
}: Props) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<any>(null);
  const [selectedCategory, setSelectedCategory] = useState<string>("ALL");
  const [isAdvancedExpanded, setIsAdvancedExpanded] = useState(false);
  const [activeEvidenceModal, setActiveEvidenceModal] = useState<any | null>(null);
  const [activeSqlModal, setActiveSqlModal] = useState<any | null>(null);
  const [savedReportIds, setSavedReportIds] = useState<Set<string>>(new Set());
  const [savingReportId, setSavingReportId] = useState<string | null>(null);
  const [copiedSql, setCopiedSql] = useState(false);
  const [isTechDetailsOpen, setIsTechDetailsOpen] = useState(false);

  // Dynamic filter state (Issue 15.3)
  const [selectedFilters, setSelectedFilters] = useState<Record<string, any>>({});
  const [searchQuestion, setSearchQuestion] = useState("");

  // Fetch insights with optional filters
  const fetchInsights = async (force: boolean = false, customFilters?: Record<string, any>) => {
    try {
      setLoading(true);
      setError(null);
      const filtersToApply = customFilters !== undefined ? customFilters : selectedFilters;
      const res = await getDatasetInsights(undefined, force, filtersToApply);
      if (res.success) {
        setData(res);
      } else {
        setError(res.error || "Failed to analyze dataset.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to load automated dataset insights.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchInsights();
  }, [fileName]);

  const handleFilterChange = (col: string, val: string) => {
    const updated = { ...selectedFilters };
    if (val === "" || val === "ALL") {
      delete updated[col];
    } else {
      updated[col] = val;
    }
    setSelectedFilters(updated);
    fetchInsights(false, updated);
  };

  const handleClearFilters = () => {
    setSelectedFilters({});
    fetchInsights(false, {});
  };

  const handleSearchSubmit = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!searchQuestion.trim()) return;
    if (onInvestigate) {
      onInvestigate(searchQuestion.trim());
    }
  };

  const handleSaveToReports = async (insight: any) => {
    try {
      setSavingReportId(insight.id);
      await createReport(
        insight.title,
        fileName || data?.friendly_name || "Active Dataset",
        insight.title,
        insight.supporting_sql || "",
        insight.plain_explanation || insight.ai_explanation || insight.description || "",
        insight.result_evidence || []
      );
      setSavedReportIds((prev) => new Set([...prev, insight.id]));
    } catch {
      alert("Failed to save insight to reports. Please try again.");
    } finally {
      setSavingReportId(null);
    }
  };

  const handleCopySql = (sql: string) => {
    navigator.clipboard.writeText(sql);
    setCopiedSql(true);
    setTimeout(() => setCopiedSql(false), 2000);
  };

  // Safe fallback collections
  const kpis: any[] = data?.kpis || [];
  const charts: any = data?.charts || {};
  const highlights: any[] = data?.highlights || [];
  const availableFilters: any[] = data?.available_filters || [];
  const suggestedQuestions: string[] = data?.suggested_questions || [
    "Which product generated the highest revenue?",
    "Compare revenue across categories",
    "Show monthly sales trends"
  ];
  const domainLabel = data?.domain_label || "General Tabular Data";
  const insightsList: any[] = data?.insights || [];
  const keyDiscoveries: any[] = data?.key_discoveries || insightsList.slice(0, 6);
  const advancedDiscoveries: any[] = data?.advanced_discoveries || insightsList.slice(keyDiscoveries.length);

  const filteredAdvanced =
    selectedCategory === "ALL"
      ? advancedDiscoveries
      : advancedDiscoveries.filter((i) => {
          if (selectedCategory === "SCHEMA_RELATIONSHIPS") {
            return i.category === "SCHEMA_RELATIONSHIPS" || i.category === "RELATIONSHIPS";
          }
          return i.category === selectedCategory;
        });

  const ADVANCED_TABS = [
    { id: "ALL", label: "All Findings" },
    { id: "ANOMALIES", label: "Outliers & Anomalies" },
    { id: "STATISTICAL", label: "Correlations & Skew" },
    { id: "TRENDS", label: "Historical Trends" },
    { id: "SCHEMA_RELATIONSHIPS", label: "Table Connections" },
    { id: "DATA_QUALITY", label: "Data Quality" },
  ];

  const hasActiveFilters = Object.keys(selectedFilters).length > 0;

  return (
    <div className="space-y-5 text-left">
      {/* SECTION A: HEADER DOCK */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 sm:p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-9 h-9 rounded-lg bg-[#168C88]/10 text-[#168C88] flex items-center justify-center border border-[#168C88]/20 shrink-0">
              <Sparkles size={18} />
            </div>
            <div>
              <h1 className="text-base font-bold text-[#172B4D] tracking-tight flex items-center gap-2">
                <span>AI Data Analytics</span>
                <span className="text-[10px] font-semibold bg-[#168C88]/10 text-[#168C88] px-2 py-0.5 rounded-full border border-[#168C88]/20">
                  {domainLabel}
                </span>
                {data?.is_line_item && (
                  <span className="text-[10px] font-medium bg-blue-50 text-blue-700 px-2 py-0.5 rounded-full border border-blue-200" title="Consolidated at order entity level">
                    Line-Item Aware
                  </span>
                )}
              </h1>
              <p className="text-xs text-[#64748B] mt-0.5">
                Understand your dataset through important metrics, trends and comparisons for{" "}
                <strong className="text-[#172B4D] font-mono">{fileName || data?.friendly_name || "Active Dataset"}</strong>.
              </p>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2.5 shrink-0">
          {data?.analyzed_at && (
            <span className="text-[11px] text-[#64748B] hidden lg:inline">
              Analyzed {new Date(data.analyzed_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          <button
            onClick={() => fetchInsights(true)}
            disabled={loading}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-white border border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#172B4D] text-xs font-semibold cursor-pointer transition shadow-xs disabled:opacity-50"
            title="Re-run analytical discovery from live dataset"
          >
            <RefreshCw size={13} className={loading ? "animate-spin text-[#168C88]" : "text-[#64748B]"} />
            <span>{loading ? "Analyzing..." : "Refresh Analytics"}</span>
          </button>
        </div>
      </div>

      {/* DYNAMIC FILTER TOOLBAR (Section 10) */}
      {availableFilters.length > 0 && (
        <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl p-3 flex items-center justify-between gap-3 flex-wrap">
          <div className="flex items-center gap-2 flex-wrap text-xs">
            <span className="text-[11px] font-bold text-[#64748B] uppercase tracking-wider flex items-center gap-1">
              <Filter size={13} className="text-[#168C88]" />
              <span>Filters:</span>
            </span>

            {availableFilters.map((filt: any) => {
              if (filt.column === "_date_range") {
                return (
                  <div key={filt.column} className="flex items-center gap-1.5 bg-white border border-[#E2E8F0] rounded-lg px-2.5 py-1 text-xs">
                    <span className="text-[#64748B] text-[11px] font-medium">{filt.label}:</span>
                    <input
                      type="date"
                      aria-label="Start date"
                      min={filt.min_date}
                      max={filt.max_date}
                      value={selectedFilters._date_from || ""}
                      onChange={(e) => handleFilterChange("_date_from", e.target.value)}
                      className="bg-transparent text-[11px] font-semibold text-[#172B4D] focus:outline-hidden cursor-pointer"
                    />
                    <span className="text-slate-400">→</span>
                    <input
                      type="date"
                      aria-label="End date"
                      min={filt.min_date}
                      max={filt.max_date}
                      value={selectedFilters._date_to || ""}
                      onChange={(e) => handleFilterChange("_date_to", e.target.value)}
                      className="bg-transparent text-[11px] font-semibold text-[#172B4D] focus:outline-hidden cursor-pointer"
                    />
                  </div>
                );
              }

              return (
                <div key={filt.column} className="flex items-center gap-1 bg-white border border-[#E2E8F0] rounded-lg px-2 py-0.5">
                  <span className="text-[#64748B] text-[11px] font-medium">{filt.label}:</span>
                  <select
                    value={selectedFilters[filt.column] || "ALL"}
                    onChange={(e) => handleFilterChange(filt.column, e.target.value)}
                    className="bg-transparent text-xs font-semibold text-[#172B4D] focus:outline-hidden cursor-pointer"
                  >
                    <option value="ALL">All {filt.label}</option>
                    {filt.options?.map((opt: string) => (
                      <option key={opt} value={opt}>
                        {opt}
                      </option>
                    ))}
                  </select>
                </div>
              );
            })}
          </div>

          {hasActiveFilters && (
            <button
              onClick={handleClearFilters}
              className="text-xs text-rose-600 hover:text-rose-800 font-semibold flex items-center gap-1 cursor-pointer transition"
            >
              <RotateCcw size={12} />
              <span>Reset Filters</span>
            </button>
          )}
        </div>
      )}

      {/* Error state */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-red-700 text-xs flex items-center justify-between">
          <div className="flex items-center gap-2">
            <AlertTriangle size={15} />
            <span>{error}</span>
          </div>
          <button
            onClick={() => fetchInsights(true)}
            className="underline font-semibold hover:text-red-900 cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {/* SECTION B: ASK YOUR DATA (Natural Language Search) */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 shadow-xs space-y-2.5">
        <form onSubmit={handleSearchSubmit} className="relative flex items-center">
          <Search size={16} className="absolute left-3.5 text-[#64748B]" />
          <input
            type="text"
            value={searchQuestion}
            onChange={(e) => setSearchQuestion(e.target.value)}
            placeholder="Ask anything about your data (e.g. Which product generated the highest revenue?)"
            className="w-full pl-10 pr-24 py-2.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl text-xs sm:text-sm text-[#172B4D] placeholder-[#94A3B8] focus:bg-white focus:outline-hidden focus:border-[#168C88] transition shadow-inner"
          />
          <button
            type="submit"
            className="absolute right-2 bg-[#168C88] hover:bg-[#137774] text-white px-3.5 py-1.5 rounded-lg text-xs font-semibold transition cursor-pointer shadow-xs"
          >
            Ask AI
          </button>
        </form>

        {suggestedQuestions && suggestedQuestions.length > 0 && (
          <div className="flex items-center gap-1.5 overflow-x-auto pb-0.5 custom-scrollbar">
            <span className="text-[10px] font-bold text-[#64748B] uppercase tracking-wider shrink-0">
              Suggested:
            </span>
            {suggestedQuestions.map((q, idx) => (
              <button
                key={idx}
                onClick={() => onInvestigate && onInvestigate(q)}
                className="text-[11px] font-medium bg-[#F1F5F9] hover:bg-[#168C88]/10 hover:text-[#168C88] hover:border-[#168C88]/30 border border-transparent text-[#475569] px-2.5 py-1 rounded-full transition cursor-pointer whitespace-nowrap shrink-0"
              >
                ðŸ’¬ {q}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* SECTION C: KEY PERFORMANCE INDICATORS (Dynamic KPI Grid) */}
      <div className="space-y-2.5">
        <div className="flex items-center justify-between">
          <h2 className="text-xs font-bold text-[#172B4D] uppercase tracking-wider flex items-center gap-2">
            <span>Key Performance Indicators</span>
            <span className="text-[10px] font-semibold bg-[#168C88]/10 text-[#168C88] px-2 py-0.5 rounded-full border border-[#168C88]/20">
              {kpis.length} Verified Metrics
            </span>
          </h2>
        </div>

        {loading ? (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {[1, 2, 3, 4, 5, 6].map((n) => (
              <div key={n} className="bg-white border border-[#E2E8F0] rounded-xl p-4 space-y-2 animate-pulse">
                <div className="h-3 bg-slate-200 rounded w-24" />
                <div className="h-7 bg-slate-300 rounded w-32" />
                <div className="h-3 bg-slate-100 rounded w-full" />
              </div>
            ))}
          </div>
        ) : kpis.length === 0 ? (
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 text-center space-y-1">
            <p className="text-xs text-[#64748B]">No numerical KPIs detected for this dataset.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3.5">
            {kpis.map((kpi: any) => (
              <DynamicKPICard
                key={kpi.id}
                kpi={kpi}
                onViewSql={() => setActiveSqlModal({ title: kpi.title, supporting_sql: kpi.supporting_sql, display_sql: kpi.display_sql })}
              />
            ))}
          </div>
        )}
      </div>

      {/* SECTION D: PERFORMANCE OVERVIEW (Trend or Distribution Chart) */}
      {charts.overview_chart && (
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 sm:p-5 shadow-xs space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h3 className="text-xs font-bold text-[#172B4D] uppercase tracking-wider flex items-center gap-2">
                <span>{charts.overview_chart.title}</span>
                <span className="text-[10px] font-semibold bg-slate-100 text-[#64748B] px-2 py-0.5 rounded-full border border-slate-200">
                  Performance Overview
                </span>
              </h3>
              <p className="text-[11px] text-[#64748B] mt-0.5">
                Temporal aggregated values derived from verified dataset records.
              </p>
            </div>
            {charts.overview_chart.supporting_sql && (
              <button
                onClick={() => setActiveSqlModal({ title: charts.overview_chart.title, supporting_sql: charts.overview_chart.supporting_sql })}
                className="text-[11px] text-[#64748B] hover:text-[#172B4D] font-medium flex items-center gap-1 cursor-pointer transition border border-[#E2E8F0] px-2 py-0.5 rounded-md"
              >
                <Code2 size={11} />
                <span>SQL</span>
              </button>
            )}
          </div>

          <div className="pt-2">
            {charts.overview_chart.type === "line" ? (
              <InteractiveLineChart data={charts.overview_chart.data} yLabel={charts.overview_chart.y_label} />
            ) : (
              <InteractiveBarChart data={charts.overview_chart.data} />
            )}
          </div>
        </div>
      )}

      {/* SECTION E: CATEGORY AND COMPARATIVE ANALYSIS */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Category Breakdown Chart */}
        {charts.category_chart && (
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 sm:p-5 shadow-xs space-y-3 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-[#172B4D] uppercase tracking-wider flex items-center gap-1.5">
                  <BarChart3 size={13} className="text-[#168C88]" />
                  <span>{charts.category_chart.title}</span>
                </h3>
                <p className="text-[11px] text-[#64748B] mt-0.5 flex items-center gap-1.5 flex-wrap">
                  <span>Breakdown across primary categorical dimensions.</span>
                  {charts.category_chart.total_categories_count > (charts.category_chart.shown_count || 0) && (
                    <span className="text-[10px] bg-slate-100 text-slate-600 px-1.5 py-0.2 rounded border border-slate-200">
                      Top {charts.category_chart.shown_count} of {charts.category_chart.total_categories_count} shown (share based on total dataset)
                    </span>
                  )}
                </p>
              </div>
              {charts.category_chart.supporting_sql && (
                <button
                  onClick={() => setActiveSqlModal({ title: charts.category_chart.title, supporting_sql: charts.category_chart.display_sql || charts.category_chart.supporting_sql, display_sql: charts.category_chart.display_sql })}
                  className="text-[11px] text-[#64748B] hover:text-[#172B4D] font-medium flex items-center gap-1 cursor-pointer transition border border-[#E2E8F0] px-2 py-0.5 rounded-md"
                >
                  <Code2 size={11} />
                  <span>SQL</span>
                </button>
              )}
            </div>

            <div className="pt-2">
              <InteractiveBarChart data={charts.category_chart.data} />
            </div>
          </div>
        )}

        {/* Distribution Donut Chart */}
        {charts.distribution_chart && (
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 sm:p-5 shadow-xs space-y-3 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-[#172B4D] uppercase tracking-wider flex items-center gap-1.5">
                  <PieChart size={13} className="text-[#168C88]" />
                  <span>{charts.distribution_chart.title}</span>
                </h3>
                <p className="text-[11px] text-[#64748B] mt-0.5">
                  Proportional composition across verified statuses and segments.
                </p>
              </div>
              {charts.distribution_chart.supporting_sql && (
                <button
                  onClick={() => setActiveSqlModal({ title: charts.distribution_chart.title, supporting_sql: charts.distribution_chart.supporting_sql })}
                  className="text-[11px] text-[#64748B] hover:text-[#172B4D] font-medium flex items-center gap-1 cursor-pointer transition border border-[#E2E8F0] px-2 py-0.5 rounded-md"
                >
                  <Code2 size={11} />
                  <span>SQL</span>
                </button>
              )}
            </div>

            <div className="pt-2">
              <InteractiveDonutChart data={charts.distribution_chart.data} />
            </div>
          </div>
        )}

        {/* Top Entities Ranking Chart */}
        {charts.top_entities_chart && (
          <div className="bg-white border border-[#E2E8F0] rounded-xl p-4 sm:p-5 shadow-xs space-y-3 lg:col-span-2">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-xs font-bold text-[#172B4D] uppercase tracking-wider flex items-center gap-1.5">
                  <Trophy size={13} className="text-[#168C88]" />
                  <span>{charts.top_entities_chart.title}</span>
                </h3>
                <p className="text-[11px] text-[#64748B] mt-0.5">
                  Ranked leaders contributing the highest volume in this dataset.
                </p>
              </div>
              {charts.top_entities_chart.supporting_sql && (
                <button
                  onClick={() => setActiveSqlModal({ title: charts.top_entities_chart.title, supporting_sql: charts.top_entities_chart.supporting_sql })}
                  className="text-[11px] text-[#64748B] hover:text-[#172B4D] font-medium flex items-center gap-1 cursor-pointer transition border border-[#E2E8F0] px-2 py-0.5 rounded-md"
                >
                  <Code2 size={11} />
                  <span>SQL</span>
                </button>
              )}
            </div>

            <div className="pt-2">
              <InteractiveBarChart data={charts.top_entities_chart.data} />
            </div>
          </div>
        )}
      </div>

      {/* SECTION F: WHAT STANDS OUT? (Analytical Findings) */}
      {highlights && highlights.length > 0 && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-xs font-bold text-[#172B4D] uppercase tracking-wider flex items-center gap-2">
              <span>What stands out?</span>
              <span className="text-[10px] font-semibold bg-emerald-50 text-emerald-700 px-2 py-0.5 rounded-full border border-emerald-200">
                {highlights.length} Key Takeaways
              </span>
            </h2>
            <p className="text-[11px] text-[#64748B]">
              Verified analytical findings derived from actual data queries.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
            {highlights.map((hl: any) => (
              <div
                key={hl.id}
                className="bg-white border border-[#E2E8F0] hover:border-[#168C88]/40 rounded-xl p-4 shadow-xs flex flex-col justify-between transition gap-3"
              >
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-xs font-bold text-[#172B4D]">{hl.title}</span>
                    <span className="text-[11px] font-bold text-[#168C88] bg-[#168C88]/10 px-2 py-0.5 rounded-full shrink-0">
                      {hl.metric}
                    </span>
                  </div>
                  <p className="text-xs text-[#475569] leading-relaxed">{hl.text}</p>
                </div>

                <div className="pt-2 border-t border-slate-100 flex items-center justify-between">
                  <span className="text-[10px] text-[#94A3B8] font-medium truncate max-w-[220px]">
                    {hl.suggested_question}
                  </span>
                  <button
                    onClick={() => onInvestigate && onInvestigate(hl.suggested_question)}
                    className="bg-[#168C88] hover:bg-[#137774] text-white px-2.5 py-1 rounded-md text-[11px] font-semibold transition cursor-pointer flex items-center gap-1 shadow-xs shrink-0"
                  >
                    <Search size={11} />
                    <span>Investigate</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* SECTION G: ADVANCED ANALYSIS (Expandable Statistical Container) */}
      <div className="pt-3 border-t border-[#E2E8F0] space-y-3">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-xs font-bold text-[#172B4D] uppercase tracking-wider flex items-center gap-2">
              <span>Advanced Analysis</span>
              <span className="text-[10px] font-semibold bg-slate-100 text-[#64748B] px-2 py-0.5 rounded-full border border-slate-200">
                {advancedDiscoveries.length} Technical Discoveries
              </span>
            </h3>
            <p className="text-[11px] text-[#64748B] mt-0.5">
              Outlier fences, bivariate correlations, skewness coefficients, and schema relationships.
            </p>
          </div>

          <button
            onClick={() => setIsAdvancedExpanded(!isAdvancedExpanded)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#E2E8F0] bg-white hover:bg-[#F8FAFC] text-xs font-semibold text-[#172B4D] cursor-pointer transition shadow-xs"
          >
            <span>{isAdvancedExpanded ? "Hide Advanced Analysis" : `Show Advanced Analysis (${advancedDiscoveries.length})`}</span>
            {isAdvancedExpanded ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
          </button>
        </div>

        {isAdvancedExpanded && (
          <div className="space-y-4 pt-1 animate-in fade-in duration-200">
            {/* Filter Tabs within Advanced Analysis */}
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 custom-scrollbar">
              {ADVANCED_TABS.map((tab) => {
                const isActive = selectedCategory === tab.id;
                return (
                  <button
                    key={tab.id}
                    onClick={() => setSelectedCategory(tab.id)}
                    className={`px-3 py-1 rounded-lg text-xs font-semibold transition cursor-pointer ${
                      isActive
                        ? "bg-[#172B4D] text-white"
                        : "bg-white text-[#64748B] hover:text-[#172B4D] border border-[#E2E8F0]"
                    }`}
                  >
                    {tab.label}
                  </button>
                );
              })}
            </div>

            {filteredAdvanced.length === 0 ? (
              <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 text-center text-xs text-[#64748B]">
                No technical discoveries matching this category.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                {filteredAdvanced.map((ins: any) => (
                  <InsightCard
                    key={ins.id}
                    insight={ins}
                    onInvestigate={(q) => {
                      if (onInvestigate) {
                        const targetQ = q || ins.suggested_questions?.[0] || ins.title;
                        onInvestigate(targetQ, ins.suggested_questions);
                      }
                    }}
                    onViewEvidence={() => {
                      setIsTechDetailsOpen(false);
                      setActiveEvidenceModal(ins);
                    }}
                    onViewSql={() => setActiveSqlModal(ins)}
                    onSaveReport={() => handleSaveToReports(ins)}
                    isSaved={savedReportIds.has(ins.id)}
                    isSaving={savingReportId === ins.id}
                  />
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* EVIDENCE DRAWER / MODAL */}
      {activeEvidenceModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#241C20]/60 backdrop-blur-xs">
          <div className="bg-white border border-[#E2E8F0] rounded-2xl p-5 sm:p-6 w-full max-w-2xl max-h-[85vh] flex flex-col shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0] shrink-0">
              <div className="flex items-center gap-2">
                <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-[#168C88]/10 text-[#168C88]">
                  {formatCategoryBadge(activeEvidenceModal.category)}
                </span>
                <h3 className="text-sm font-bold text-[#172B4D] truncate">
                  Evidence: {activeEvidenceModal.title}
                </h3>
              </div>
              <button
                onClick={() => setActiveEvidenceModal(null)}
                className="w-7 h-7 rounded-full bg-[#F1F5F9] hover:bg-[#E2E8F0] flex items-center justify-center text-[#64748B] hover:text-[#172B4D] transition cursor-pointer"
              >
                <X size={14} />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto custom-scrollbar py-3 space-y-3.5 text-xs text-[#172B4D]">
              <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl p-3">
                <span className="text-[10px] font-bold text-[#64748B] uppercase tracking-wider block mb-1">
                  What PromptSQL Discovered
                </span>
                <p className="leading-relaxed font-medium text-[#172B4D]">
                  {activeEvidenceModal.plain_explanation || activeEvidenceModal.ai_explanation || activeEvidenceModal.description}
                </p>
              </div>

              {activeEvidenceModal.why_it_matters && (
                <div className="bg-emerald-50/50 border border-emerald-200/60 rounded-xl p-3 text-emerald-950">
                  <span className="text-[10px] font-bold text-emerald-700 uppercase tracking-wider block mb-1 flex items-center gap-1">
                    <Sparkles size={11} className="text-emerald-600" />
                    {activeEvidenceModal.category === "ANOMALIES" ? "What to investigate" : "Why this matters"}
                  </span>
                  <p className="leading-relaxed">{activeEvidenceModal.why_it_matters}</p>
                </div>
              )}

              {activeEvidenceModal.result_evidence && activeEvidenceModal.result_evidence.length > 0 && (
                <div>
                  <span className="text-[10px] font-bold text-[#64748B] uppercase tracking-wider block mb-1">
                    Verified Supporting Records ({activeEvidenceModal.result_evidence.length} entries)
                  </span>
                  <div className="border border-[#E2E8F0] rounded-lg overflow-x-auto custom-scrollbar max-h-48">
                    <table className="w-full text-left text-[11px] border-collapse">
                      <thead className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-[#64748B] font-semibold">
                        <tr>
                          {Object.keys(activeEvidenceModal.result_evidence[0] || {}).map((col) => (
                            <th key={col} className="p-2 border-r border-[#E2E8F0] last:border-r-0 whitespace-nowrap">
                              {col}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {activeEvidenceModal.result_evidence.map((row: any, rIdx: number) => (
                          <tr key={rIdx} className="border-b border-[#E2E8F0] last:border-b-0 hover:bg-[#F8FAFC]">
                            {Object.values(row).map((val: any, cIdx: number) => (
                              <td key={cIdx} className="p-2 border-r border-[#E2E8F0] last:border-r-0 whitespace-nowrap font-mono text-[10px]">
                                {val !== null ? String(val) : <span className="text-slate-400 italic">NULL</span>}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {/* Collapsible Technical Details */}
              <div className="border border-[#E2E8F0] rounded-xl overflow-hidden">
                <button
                  onClick={() => setIsTechDetailsOpen(!isTechDetailsOpen)}
                  className="w-full p-2.5 bg-[#F8FAFC] hover:bg-[#F1F5F9] flex items-center justify-between text-xs font-semibold text-[#172B4D] cursor-pointer transition"
                >
                  <span className="flex items-center gap-1.5">
                    <Code2 size={13} className="text-[#168C88]" />
                    <span>Technical & Statistical Calculation Details</span>
                  </span>
                  {isTechDetailsOpen ? <ChevronUp size={14} /> : <ChevronDown size={14} />}
                </button>

                {isTechDetailsOpen && (
                  <div className="p-3 bg-white space-y-2 border-t border-[#E2E8F0]">
                    <div className="space-y-1">
                      <span className="text-[10px] font-bold text-[#64748B] uppercase tracking-wider block">
                        Algorithm & Detection Method
                      </span>
                      <p className="font-mono text-[11px] text-[#475569]">
                        {activeEvidenceModal.detection_method || activeEvidenceModal.subcategory}
                      </p>
                    </div>

                    {activeEvidenceModal.supporting_sql && (
                      <div className="space-y-1">
                        <span className="text-[10px] font-bold text-[#64748B] uppercase tracking-wider block">
                          Supporting SQL Query
                        </span>
                        <pre className="p-2.5 bg-[#172B4D] text-[#E2E8F0] rounded-lg text-[10px] font-mono overflow-x-auto whitespace-pre-wrap">
                          {activeEvidenceModal.display_sql || activeEvidenceModal.supporting_sql}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            </div>

            <div className="pt-3 border-t border-[#E2E8F0] flex items-center justify-end gap-2 shrink-0">
              <button
                onClick={() => setActiveEvidenceModal(null)}
                className="px-4 py-1.5 rounded-lg border border-[#E2E8F0] hover:bg-[#F8FAFC] text-xs font-semibold text-[#172B4D] cursor-pointer transition"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* SQL INSPECTION MODAL */}
      {activeSqlModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-[#241C20]/60 backdrop-blur-xs">
          <div className="bg-white border border-[#E2E8F0] rounded-2xl p-5 sm:p-6 w-full max-w-2xl flex flex-col shadow-2xl animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
              <div className="flex items-center gap-2">
                <Code2 size={16} className="text-[#168C88]" />
                <h3 className="text-sm font-bold text-[#172B4D]">
                  SQL: {activeSqlModal.title}
                </h3>
              </div>
              <button
                onClick={() => setActiveSqlModal(null)}
                className="w-7 h-7 rounded-full bg-[#F1F5F9] hover:bg-[#E2E8F0] flex items-center justify-center text-[#64748B] hover:text-[#172B4D] transition cursor-pointer"
              >
                <X size={14} />
              </button>
            </div>

            <div className="my-4">
              <pre className="p-3 bg-[#172B4D] text-emerald-400 rounded-xl text-xs font-mono overflow-x-auto whitespace-pre-wrap">
                {activeSqlModal.display_sql || activeSqlModal.supporting_sql}
              </pre>
            </div>

            <div className="flex items-center justify-between pt-2 border-t border-[#E2E8F0]">
              <button
                onClick={() => handleCopySql(activeSqlModal.display_sql || activeSqlModal.supporting_sql)}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#E2E8F0] hover:bg-[#F8FAFC] text-xs font-semibold text-[#172B4D] cursor-pointer transition"
              >
                {copiedSql ? <Check size={13} className="text-emerald-600" /> : <Copy size={13} />}
                <span>{copiedSql ? "Copied!" : "Copy SQL"}</span>
              </button>
              <button
                onClick={() => setActiveSqlModal(null)}
                className="px-4 py-1.5 rounded-lg bg-[#168C88] hover:bg-[#137774] text-white text-xs font-semibold cursor-pointer transition shadow-xs"
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Dynamic KPI Card Component (Section C)
// ---------------------------------------------------------------------------
function DynamicKPICard({
  kpi,
  onViewSql,
}: {
  kpi: any;
  onViewSql: () => void;
}) {
  const getIcon = (iconName?: string) => {
    switch (iconName) {
      case "DollarSign":
        return <DollarSign size={16} />;
      case "ShoppingCart":
        return <ShoppingCart size={16} />;
      case "TrendingUp":
        return <TrendingUp size={16} />;
      case "Award":
        return <Award size={16} />;
      case "Package":
        return <Package size={16} />;
      case "Users":
        return <Users size={16} />;
      case "GraduationCap":
        return <GraduationCap size={16} />;
      case "Trophy":
        return <Trophy size={16} />;
      case "AlertCircle":
        return <AlertCircle size={16} />;
      case "CheckCircle":
        return <CheckCircle size={16} />;
      case "BookOpen":
        return <BookOpen size={16} />;
      case "Briefcase":
        return <Briefcase size={16} />;
      case "Building":
        return <Building size={16} />;
      case "MapPin":
        return <MapPin size={16} />;
      default:
        return <Layers size={16} />;
    }
  };

  const comp = kpi.period_comparison;

  return (
    <div className="bg-white border border-[#E2E8F0] hover:border-[#168C88]/40 rounded-xl p-4 shadow-xs flex flex-col justify-between transition group">
      <div>
        <div className="flex items-center justify-between gap-2 mb-2">
          <div className="flex items-center gap-1.5">
            <div className="w-7 h-7 rounded-lg bg-[#168C88]/10 text-[#168C88] flex items-center justify-center shrink-0">
              {getIcon(kpi.icon)}
            </div>
            <span className="text-[10px] font-bold text-[#64748B] uppercase tracking-wider truncate">
              {kpi.title}
            </span>
          </div>

          <button
            onClick={onViewSql}
            className="text-[10px] text-[#94A3B8] hover:text-[#172B4D] transition cursor-pointer flex items-center gap-0.5"
            title="Inspect supporting SQL calculation"
          >
            <Code2 size={12} />
          </button>
        </div>

        <div className="text-2xl font-bold text-[#172B4D] tracking-tight">
          {kpi.value}
        </div>

        {kpi.currency_breakdown && kpi.currency_breakdown.length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {kpi.currency_breakdown.map((item: any, idx: number) => (
              <span
                key={idx}
                className="text-[11px] font-medium px-2 py-0.5 rounded bg-slate-50 text-slate-700 border border-slate-200"
              >
                <span className="font-bold text-slate-900">{item.code}:</span> {item.formatted || `${item.symbol}${item.amount}`}
              </span>
            ))}
          </div>
        )}

        {kpi.is_ambiguous && (
          <div className="mt-2 text-[11px] text-amber-700 bg-amber-50 border border-amber-200 rounded p-1.5 leading-snug">
            {kpi.explanation || "Metric aggregation grain is ambiguous."}
          </div>
        )}

        <p className="text-[11px] text-[#64748B] mt-1 line-clamp-2 leading-relaxed">
          {kpi.description}
        </p>
      </div>

      {comp && (
        <div
          className="mt-3 pt-2 border-t border-slate-100 flex items-center justify-between gap-1.5"
          title={
            comp.narrative ||
            `${comp.metric_name || kpi.title}: ${comp.current_value} vs ${comp.previous_value}`
          }
        >
          <div className="flex items-center gap-1.5 truncate">
            {comp.change_pct !== null && comp.change_pct !== undefined ? (
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full flex items-center gap-0.5 shrink-0 ${
                  comp.change_pct >= 0 ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                }`}
              >
                {comp.change_pct >= 0 ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                {comp.change_pct >= 0 ? "+" : ""}{comp.change_pct}%
              </span>
            ) : comp.absolute_change !== null && comp.absolute_change !== undefined ? (
              <span
                className={`text-[10px] font-bold px-1.5 py-0.5 rounded-full flex items-center gap-0.5 shrink-0 ${
                  comp.absolute_change >= 0 ? "bg-emerald-50 text-emerald-700" : "bg-rose-50 text-rose-700"
                }`}
              >
                {comp.absolute_change >= 0 ? <ArrowUpRight size={10} /> : <ArrowDownRight size={10} />}
                {comp.previous_value === 0 ? "New" : `${comp.absolute_change >= 0 ? "+" : ""}${comp.absolute_change}`}
              </span>
            ) : (
              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded-full bg-slate-100 text-slate-500 shrink-0">
                Unavailable
              </span>
            )}
            <span className="text-[10px] text-[#94A3B8] truncate">{comp.period_label}</span>
          </div>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Interactive SVG Line Chart (Section D)
// ---------------------------------------------------------------------------
function InteractiveLineChart({
  data,
  yLabel = "Value",
}: {
  data: { label: string; value: number }[];
  yLabel?: string;
}) {
  if (!data || data.length < 2) {
    return <div className="text-xs text-[#94A3B8] py-8 text-center">Not enough data points for trend chart.</div>;
  }

  const values = data.map((d) => d.value);
  const minVal = Math.min(...values);
  const maxVal = Math.max(...values);
  const range = maxVal - minVal || 1;

  const width = 600;
  const height = 180;
  const padLeft = 55;
  const padRight = 20;
  const padTop = 15;
  const padBottom = 30;

  const chartW = width - padLeft - padRight;
  const chartH = height - padTop - padBottom;

  const points = data.map((d, idx) => {
    const x = padLeft + (idx / (data.length - 1)) * chartW;
    const y = padTop + chartH - ((d.value - minVal) / range) * chartH;
    return { x, y, label: d.label, value: d.value };
  });

  const pathD = points.reduce((acc, p, i) => `${acc} ${i === 0 ? "M" : "L"} ${p.x.toFixed(1)},${p.y.toFixed(1)}`, "");
  const areaD = `${pathD} L ${points[points.length - 1].x.toFixed(1)},${height - padBottom} L ${points[0].x.toFixed(1)},${height - padBottom} Z`;

  const formatShort = (v: number) => {
    if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M`;
    if (v >= 1_000) return `${(v / 1_000).toFixed(0)}K`;
    return v.toFixed(0);
  };

  return (
    <div className="w-full overflow-hidden">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#168C88" stopOpacity="0.28" />
            <stop offset="100%" stopColor="#168C88" stopOpacity="0.0" />
          </linearGradient>
        </defs>

        {/* Horizontal gridlines */}
        {[0, 0.5, 1].map((pct, idx) => {
          const y = padTop + chartH * (1 - pct);
          const val = minVal + range * pct;
          return (
            <g key={idx}>
              <line x1={padLeft} y1={y} x2={width - padRight} y2={y} stroke="#E2E8F0" strokeDasharray="3,3" />
              <text x={padLeft - 8} y={y + 3} textAnchor="end" className="text-[9px] fill-[#94A3B8] font-mono">
                {formatShort(val)}
              </text>
            </g>
          );
        })}

        {/* Filled gradient area */}
        <path d={areaD} fill="url(#areaGrad)" />

        {/* Trend stroke */}
        <path d={pathD} fill="none" stroke="#168C88" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />

        {/* Data points & X-axis labels */}
        {points.map((p, idx) => (
          <g key={idx} className="group">
            <circle cx={p.x} cy={p.y} r="3.5" fill="#FFFFFF" stroke="#168C88" strokeWidth="2" className="transition-all hover:r-5 cursor-pointer" />
            <title>{`${p.label}: ${p.value.toLocaleString()} (${yLabel})`}</title>
            {(idx === 0 || idx === Math.floor(points.length / 2) || idx === points.length - 1) && (
              <text x={p.x} y={height - 10} textAnchor="middle" className="text-[9px] fill-[#64748B] font-mono">
                {p.label}
              </text>
            )}
          </g>
        ))}
      </svg>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Interactive Bar Chart (Section E)
// ---------------------------------------------------------------------------
function InteractiveBarChart({
  data,
}: {
  data: { label: string; value: number; volume?: number }[];
}) {
  if (!data || data.length === 0) return null;
  const maxVal = Math.max(...data.map((d) => d.value), 1);

  const formatShort = (v: number) => {
    if (v >= 1_000_000) return `$${(v / 1_000_000).toFixed(2)}M`;
    if (v >= 1_000) return `$${(v / 1_000).toFixed(1)}K`;
    return v.toLocaleString();
  };

  return (
    <div className="space-y-2.5">
      {data.slice(0, 6).map((item, idx) => {
        const pct = Math.max(8, Math.min(100, Math.round((item.value / maxVal) * 100)));
        return (
          <div key={idx} className="space-y-1">
            <div className="flex items-center justify-between text-xs">
              <span className="font-medium text-[#172B4D] truncate max-w-[200px]" title={item.label}>
                {item.label}
              </span>
              <span className="font-bold text-[#168C88] text-[11px]">
                {formatShort(item.value)}
                {item.volume !== undefined && (
                  <span className="text-[#94A3B8] font-normal ml-1">({item.volume} records)</span>
                )}
              </span>
            </div>
            <div className="w-full bg-[#F1F5F9] rounded-md h-2.5 overflow-hidden">
              <div
                className="bg-[#168C88] h-full rounded-md transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Interactive Donut Chart (Section E)
// ---------------------------------------------------------------------------
function InteractiveDonutChart({
  data,
}: {
  data: { label: string; value: number }[];
}) {
  if (!data || data.length === 0) return null;

  const total = data.reduce((acc, d) => acc + d.value, 0) || 1;
  const colors = ["#168C88", "#3B82F6", "#8B5CF6", "#F59E0B", "#EC4899", "#10B981"];

  const radius = 55;
  const circumference = 2 * Math.PI * radius;
  let accumulated = 0;

  return (
    <div className="flex items-center justify-around gap-4 flex-wrap sm:flex-nowrap">
      <div className="relative w-36 h-36 shrink-0 flex items-center justify-center">
        <svg viewBox="0 0 140 140" className="w-full h-full -rotate-90">
          {data.map((item, idx) => {
            const dash = (item.value / total) * circumference;
            const offset = -accumulated;
            accumulated += dash;
            return (
              <circle
                key={idx}
                cx="70"
                cy="70"
                r={radius}
                fill="transparent"
                stroke={colors[idx % colors.length]}
                strokeWidth="20"
                strokeDasharray={`${dash} ${circumference}`}
                strokeDashoffset={offset}
                className="transition-all duration-300 hover:opacity-85"
              />
            );
          })}
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center text-center">
          <span className="text-sm font-bold text-[#172B4D]">{total.toLocaleString()}</span>
          <span className="text-[9px] text-[#64748B] uppercase tracking-wider font-semibold">Total</span>
        </div>
      </div>

      <div className="space-y-1.5 text-xs flex-1 max-w-[240px]">
        {data.slice(0, 5).map((item, idx) => {
          const pct = Math.round((item.value / total) * 100);
          return (
            <div key={idx} className="flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5 truncate">
                <span className="w-2.5 h-2.5 rounded-full shrink-0" style={{ backgroundColor: colors[idx % colors.length] }} />
                <span className="text-[#475569] font-medium truncate" title={item.label}>
                  {item.label}
                </span>
              </div>
              <span className="font-bold text-[#172B4D] text-[11px] shrink-0">
                {item.value.toLocaleString()} <span className="text-[#94A3B8] font-normal">({pct}%)</span>
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Advanced Technical Insight Card Component (Section G)
// ---------------------------------------------------------------------------
function formatCategoryBadge(cat: string): string {
  switch (cat) {
    case "ANOMALIES":
      return "Outliers & Anomalies";
    case "STATISTICAL":
      return "Correlations & Patterns";
    case "TRENDS":
      return "Historical Trends";
    case "BUSINESS":
      return "Operational Findings";
    case "DATA_QUALITY":
      return "Data Quality";
    case "SCHEMA_RELATIONSHIPS":
    case "RELATIONSHIPS":
      return "Table Connections";
    default:
      return "Technical Finding";
  }
}

function InsightCard({
  insight,
  onInvestigate,
  onViewEvidence,
  onViewSql,
  onSaveReport,
  isSaved,
  isSaving,
}: {
  insight: any;
  onInvestigate: (question?: string) => void;
  onViewEvidence: () => void;
  onViewSql: () => void;
  onSaveReport: () => void;
  isSaved: boolean;
  isSaving: boolean;
}) {
  return (
    <div className="bg-white border border-[#E2E8F0] hover:border-[#168C88]/40 rounded-xl p-4 shadow-xs flex flex-col justify-between transition group">
      <div className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded bg-slate-100 text-[#64748B]">
            {formatCategoryBadge(insight.category)}
          </span>
          {insight.metric_formatted && (
            <span className="text-[11px] font-bold text-[#168C88] bg-[#168C88]/10 px-2 py-0.5 rounded-full">
              {insight.metric_formatted}
            </span>
          )}
        </div>

        <h4 className="text-xs font-bold text-[#172B4D] group-hover:text-[#168C88] transition leading-snug">
          {insight.title}
        </h4>

        <p className="text-xs text-[#475569] leading-relaxed">
          {insight.plain_explanation || insight.ai_explanation || insight.description}
        </p>

        {insight.why_it_matters && (
          <p className="text-[11px] text-[#64748B] italic bg-[#F8FAFC] p-2 rounded-lg border border-slate-100">
            {insight.why_it_matters}
          </p>
        )}
      </div>

      <div className="pt-3 mt-3 border-t border-[#E2E8F0] flex items-center justify-between gap-1 flex-wrap">
        <button
          onClick={() => onInvestigate()}
          className="bg-[#168C88] hover:bg-[#137774] text-white px-2.5 py-1 rounded-md text-[11px] font-semibold transition cursor-pointer flex items-center gap-1 shadow-xs"
        >
          <Search size={11} />
          <span>Investigate</span>
        </button>

        <div className="flex items-center gap-1">
          <button
            onClick={onViewEvidence}
            className="border border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#64748B] hover:text-[#172B4D] px-2 py-1 rounded text-[10px] font-medium transition cursor-pointer flex items-center gap-1"
          >
            <Table size={11} />
            <span>Evidence</span>
          </button>
          <button
            onClick={onViewSql}
            className="border border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#64748B] hover:text-[#172B4D] px-2 py-1 rounded text-[10px] font-medium transition cursor-pointer flex items-center gap-1"
          >
            <Code2 size={11} />
            <span>SQL</span>
          </button>
          <button
            onClick={onSaveReport}
            disabled={isSaved || isSaving}
            className={`border px-2 py-1 rounded text-[10px] font-medium transition cursor-pointer flex items-center gap-1 ${
              isSaved ? "bg-emerald-50 border-emerald-200 text-emerald-700" : "border-[#E2E8F0] hover:bg-[#F8FAFC] text-[#64748B]"
            }`}
          >
            {isSaved ? <Check size={11} /> : <FolderHeart size={11} />}
            <span>{isSaved ? "Saved" : "Save"}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
