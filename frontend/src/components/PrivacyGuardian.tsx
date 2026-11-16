import { useState, useEffect } from "react";
import {
  Shield,
  ShieldCheck,
  Lock,
  AlertCircle,
  RefreshCw,
  Search,
  CheckCircle2,
  Clock,
  Eye,
  Activity,
  Info,
  Sliders,
  Check,
  AlertTriangle
} from "lucide-react";
import {
  getPrivacyOverview,
  rescanPrivacy,
  updatePrivacyPolicy,
  getPrivacyAuditLogs
} from "../services/api";
import type {
  PrivacyOverviewResponse,
  PrivacyAuditRecord
} from "../services/api";

interface Props {
  fileName?: string;
  onRefresh?: () => void;
}

export default function PrivacyGuardian({ fileName, onRefresh }: Props) {
  const [loading, setLoading] = useState<boolean>(true);
  const [rescanning, setRescanning] = useState<boolean>(false);
  const [data, setData] = useState<PrivacyOverviewResponse | null>(null);
  const [auditLogs, setAuditLogs] = useState<PrivacyAuditRecord[]>([]);
  const [activeTab, setActiveTab] = useState<"all" | "sensitive" | "restricted" | "review">("all");
  const [searchQuery, setSearchQuery] = useState<string>("");
  const [showAuditModal, setShowAuditModal] = useState<boolean>(false);
  const [toastMessage, setToastMessage] = useState<string | null>(null);
  const [updatingColumn, setUpdatingColumn] = useState<string | null>(null);

  const fetchOverview = async (isRescan: boolean = false) => {
    try {
      if (isRescan) setRescanning(true);
      else setLoading(true);

      const res = isRescan ? await rescanPrivacy() : await getPrivacyOverview();
      setData(res);

      // Fetch audit logs in background
      try {
        const auditRes = await getPrivacyAuditLogs(20);
        if (auditRes.success) {
          setAuditLogs(auditRes.logs || []);
        }
      } catch (ae) {
        console.error("Failed fetching audit logs:", ae);
      }
      if (isRescan && onRefresh) {
        onRefresh();
      }
    } catch (err: any) {
      console.error("Privacy Guardian load error:", err);
      showToast(err.message || "Failed to load privacy details", true);
    } finally {
      setLoading(false);
      setRescanning(false);
    }
  };

  useEffect(() => {
    fetchOverview(false);
  }, [fileName]);

  const [toastIsError, setToastIsError] = useState(false);

  const showToast = (msg: string, isError: boolean = false) => {
    setToastMessage(msg);
    setToastIsError(isError);
    setTimeout(() => setToastMessage(null), 3500);
  };

  const handlePolicyChange = async (columnName: string, newPolicy: string) => {
    try {
      setUpdatingColumn(columnName);
      await updatePrivacyPolicy(columnName, newPolicy);
      
      // Update local state optimistically
      if (data) {
        const updatedColumns = data.columns.map((col) => {
          if (col.column_name === columnName) {
            const newStatus = newPolicy === "normal" ? "normal" : newPolicy === "custom" ? "configured" : "protected";
            return {
              ...col,
              policy: newPolicy as any,
              status: newStatus as any
            };
          }
          return col;
        });

        const sensitiveCount = updatedColumns.filter((c) => c.policy === "sensitive").length;
        const restrictedCount = updatedColumns.filter((c) => c.policy === "restricted").length;
        const reviewCount = updatedColumns.filter((c) => c.confidence === "requires_review" || c.status === "pending_review").length;

        setData({
          ...data,
          columns: updatedColumns,
          sensitive_columns_count: sensitiveCount,
          restricted_columns_count: restrictedCount,
          review_required_count: reviewCount
        });
      }

      showToast(`Updated policy for '${columnName}' to ${newPolicy.toUpperCase()}`);

      // Refresh audit logs
      const auditRes = await getPrivacyAuditLogs(20);
      if (auditRes.success) {
        setAuditLogs(auditRes.logs || []);
      }
    } catch (err: any) {
      showToast(err.message || "Failed to update policy", true);
    } finally {
      setUpdatingColumn(null);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center p-16 space-y-4 bg-white rounded-2xl border border-slate-200/80 shadow-sm min-h-[400px]">
        <div className="relative">
          <div className="w-14 h-14 rounded-full border-4 border-emerald-500/20 border-t-emerald-600 animate-spin" />
          <Shield className="w-6 h-6 text-emerald-600 absolute inset-0 m-auto animate-pulse" />
        </div>
        <p className="text-slate-600 font-medium">Scanning dataset schema & enforcing privacy policies...</p>
      </div>
    );
  }

  const columns = data?.columns || [];
  const filteredColumns = columns.filter((col) => {
    // Filter by tab
    if (activeTab === "sensitive" && col.policy !== "sensitive") return false;
    if (activeTab === "restricted" && col.policy !== "restricted") return false;
    if (activeTab === "review" && col.confidence !== "requires_review" && col.status !== "pending_review") return false;

    // Filter by search query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase();
      return (
        col.column_name.toLowerCase().includes(q) ||
        col.detected_category.toLowerCase().includes(q) ||
        col.policy.toLowerCase().includes(q) ||
        (col.explanation && col.explanation.toLowerCase().includes(q))
      );
    }
    return true;
  });

  const getCategoryBadge = (cat: string) => {
    switch (cat) {
      case "personal_identification":
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200/60">Personal ID</span>;
      case "government_identification":
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200/60">Govt ID</span>;
      case "financial_information":
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200/60">Financial</span>;
      case "confidential_business":
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200/60">Confidential</span>;
      case "credentials_security":
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-red-50 text-red-800 border border-red-200/60">Credentials</span>;
      case "medical_information":
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold bg-cyan-50 text-cyan-700 border border-cyan-200/60">Medical</span>;
      case "internal_identifier":
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200/60">Internal Key</span>;
      default:
        return <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-slate-50 text-slate-600 border border-slate-200/60">Standard</span>;
    }
  };

  const getConfidenceBadge = (conf: string) => {
    switch (conf) {
      case "high":
        return <span className="inline-flex items-center gap-1 text-xs font-medium text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200/60"><Check className="w-3 h-3" /> High</span>;
      case "medium":
        return <span className="inline-flex items-center gap-1 text-xs font-medium text-amber-700 bg-amber-50 px-2 py-0.5 rounded border border-amber-200/60">Medium</span>;
      case "requires_review":
        return <span className="inline-flex items-center gap-1 text-xs font-medium text-purple-700 bg-purple-50 px-2 py-0.5 rounded border border-purple-200/60"><AlertTriangle className="w-3 h-3" /> Needs Review</span>;
      default:
        return <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 bg-slate-100 px-2 py-0.5 rounded border border-slate-200/60">Low</span>;
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "protected":
        return (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded-full border border-emerald-200/70">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" /> Protected
          </span>
        );
      case "pending_review":
        return (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-amber-700 bg-amber-50 px-2.5 py-1 rounded-full border border-amber-200/70">
            <Clock className="w-3.5 h-3.5 text-amber-600" /> Pending Review
          </span>
        );
      case "configured":
        return (
          <span className="inline-flex items-center gap-1 text-xs font-semibold text-blue-700 bg-blue-50 px-2.5 py-1 rounded-full border border-blue-200/70">
            <Sliders className="w-3.5 h-3.5 text-blue-600" /> Configured
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 text-xs font-medium text-slate-600 bg-slate-100 px-2.5 py-1 rounded-full border border-slate-200/60">
            <CheckCircle2 className="w-3.5 h-3.5 text-slate-500" /> Normal
          </span>
        );
    }
  };

  return (
    <div className="space-y-5">
      {/* Toast Notification */}
      {toastMessage && (
        <div className={`fixed bottom-6 right-6 z-50 flex items-center gap-2 px-4 py-3 rounded-xl shadow-xl border transition-all duration-300 text-sm font-medium ${
          toastIsError
            ? "bg-rose-950 text-rose-100 border-rose-800"
            : "bg-slate-900 text-white border-slate-800"
        }`}>
          {toastIsError ? (
            <AlertTriangle className="w-4 h-4 text-rose-400" />
          ) : (
            <Info className="w-4 h-4 text-emerald-400" />
          )}
          <span>{toastMessage}</span>
        </div>
      )}

      {/* Header Banner */}
      <div className="bg-gradient-to-r from-emerald-900 via-slate-900 to-indigo-950 rounded-2xl p-6 text-white shadow-sm border border-emerald-800/40 relative overflow-hidden">
        <div className="absolute top-0 right-0 w-96 h-96 bg-emerald-500/10 rounded-full blur-3xl pointer-events-none -mr-20 -mt-20" />
        
        <div className="relative z-10 flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1.5">
            <div className="flex items-center gap-2.5">
              <div className="p-2 bg-emerald-500/20 rounded-xl border border-emerald-400/30">
                <ShieldCheck className="w-6 h-6 text-emerald-400" />
              </div>
              <div>
                <h1 className="text-xl font-bold tracking-tight text-white flex items-center gap-2">
                  Privacy Guardian
                  <span className="text-xs px-2.5 py-0.5 rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-400/30 font-semibold uppercase tracking-wider">
                    AI Boundary Protection
                  </span>
                </h1>
                <p className="text-xs text-slate-300">
                  Active Dataset: <span className="font-semibold text-white">{data?.friendly_name || fileName}</span>
                  {data?.last_scanned_at && (
                    <span className="ml-2 text-slate-400">
                      • Last Scanned: {new Date(data.last_scanned_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  )}
                </p>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-2.5 self-start md:self-auto">
            <button
              onClick={() => setShowAuditModal(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold rounded-xl bg-white/10 hover:bg-white/15 text-white border border-white/15 transition-all shadow-sm"
            >
              <Activity className="w-3.5 h-3.5 text-emerald-300" />
              Audit Trail ({auditLogs.length})
            </button>
            <button
              onClick={() => fetchOverview(true)}
              disabled={rescanning}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl bg-emerald-500 hover:bg-emerald-400 text-slate-950 font-bold transition-all shadow-sm disabled:opacity-60"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${rescanning ? "animate-spin" : ""}`} />
              {rescanning ? "Scanning..." : "Rescan Dataset"}
            </button>
          </div>
        </div>

        {/* Fundamental Principle Info Bar */}
        <div className="mt-4 pt-4 border-t border-white/10 flex items-start gap-2.5 text-xs text-slate-300">
          <Info className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
          <p>
            <strong className="text-white">Zero Data Loss Principle:</strong> Authorized users retain complete, unmasked access to all original records in Data Table, Queries, and Exports. Sensitive and restricted values are redacted or excluded strictly at the external AI transmission boundary.
          </p>
        </div>
      </div>

      {/* 4 Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Scanned Columns */}
        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Columns Scanned</p>
            <p className="text-2xl font-bold text-slate-900 mt-1">{data?.columns_scanned || 0}</p>
            <p className="text-xs text-slate-400 mt-0.5">Total schema attributes</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-slate-100 flex items-center justify-center text-slate-600">
            <Eye className="w-6 h-6" />
          </div>
        </div>

        {/* Sensitive Columns */}
        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Sensitive Columns</p>
            <p className="text-2xl font-bold text-emerald-600 mt-1">{data?.sensitive_columns_count || 0}</p>
            <p className="text-xs text-emerald-600/80 mt-0.5">Redacted before AI</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-emerald-50 border border-emerald-100 flex items-center justify-center text-emerald-600">
            <ShieldCheck className="w-6 h-6" />
          </div>
        </div>

        {/* Restricted Columns */}
        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Restricted Fields</p>
            <p className="text-2xl font-bold text-rose-600 mt-1">{data?.restricted_columns_count || 0}</p>
            <p className="text-xs text-rose-600/80 mt-0.5">Never sent to AI</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-rose-50 border border-rose-100 flex items-center justify-center text-rose-600">
            <Lock className="w-6 h-6" />
          </div>
        </div>

        {/* Requiring Review */}
        <div className="bg-white rounded-2xl p-4 border border-slate-200/80 shadow-sm flex items-center justify-between">
          <div>
            <p className="text-xs font-medium text-slate-500 uppercase tracking-wider">Requires Review</p>
            <p className="text-2xl font-bold text-amber-600 mt-1">{data?.review_required_count || 0}</p>
            <p className="text-xs text-amber-600/80 mt-0.5">Pending user review</p>
          </div>
          <div className="w-12 h-12 rounded-xl bg-amber-50 border border-amber-100 flex items-center justify-center text-amber-600">
            <AlertCircle className="w-6 h-6" />
          </div>
        </div>
      </div>

      {/* Main Content Workspace */}
      <div className="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        {/* Filter and Search Bar */}
        <div className="p-4 border-b border-slate-200/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {/* Filter Tabs */}
          <div className="flex items-center gap-1.5 bg-slate-100/80 p-1 rounded-xl">
            <button
              onClick={() => setActiveTab("all")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "all"
                  ? "bg-white text-slate-900 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              All Columns ({columns.length})
            </button>
            <button
              onClick={() => setActiveTab("sensitive")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "sensitive"
                  ? "bg-white text-emerald-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Sensitive ({data?.sensitive_columns_count || 0})
            </button>
            <button
              onClick={() => setActiveTab("restricted")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "restricted"
                  ? "bg-white text-rose-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Restricted ({data?.restricted_columns_count || 0})
            </button>
            <button
              onClick={() => setActiveTab("review")}
              className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-all ${
                activeTab === "review"
                  ? "bg-white text-amber-700 shadow-sm"
                  : "text-slate-600 hover:text-slate-900"
              }`}
            >
              Requires Review ({data?.review_required_count || 0})
            </button>
          </div>

          {/* Search Box */}
          <div className="relative min-w-[240px]">
            <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
            <input
              type="text"
              placeholder="Search column, category, or policy..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-full pl-9 pr-3 py-1.5 text-xs rounded-xl border border-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/20 focus:border-emerald-500 text-slate-800"
            />
          </div>
        </div>

        {/* Table View */}
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse text-xs">
            <thead>
              <tr className="bg-slate-50/70 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider">
                <th className="py-3 px-4">Column Name</th>
                <th className="py-3 px-4">Detected Category</th>
                <th className="py-3 px-4">Confidence</th>
                <th className="py-3 px-4">Privacy Policy</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4">Detection Reason / Evidence</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filteredColumns.length === 0 ? (
                <tr>
                  <td colSpan={6} className="text-center py-10 text-slate-400">
                    No columns match the selected filter or search term.
                  </td>
                </tr>
              ) : (
                filteredColumns.map((col) => (
                  <tr
                    key={col.column_name}
                    className={`hover:bg-slate-50/80 transition-colors ${
                      updatingColumn === col.column_name ? "opacity-50" : ""
                    }`}
                  >
                    <td className="py-3 px-4 font-mono font-semibold text-slate-900">
                      {col.column_name}
                    </td>
                    <td className="py-3 px-4">
                      {getCategoryBadge(col.detected_category)}
                    </td>
                    <td className="py-3 px-4">
                      {getConfidenceBadge(col.confidence)}
                    </td>
                    <td className="py-3 px-4">
                      <select
                        value={col.policy}
                        onChange={(e) => handlePolicyChange(col.column_name, e.target.value)}
                        disabled={updatingColumn === col.column_name}
                        className={`text-xs font-semibold px-2.5 py-1 rounded-lg border focus:outline-none focus:ring-2 focus:ring-emerald-500/30 ${
                          col.policy === "sensitive"
                            ? "bg-emerald-50 text-emerald-800 border-emerald-300"
                            : col.policy === "restricted"
                            ? "bg-rose-50 text-rose-800 border-rose-300"
                            : col.policy === "custom"
                            ? "bg-blue-50 text-blue-800 border-blue-300"
                            : "bg-slate-50 text-slate-700 border-slate-200"
                        }`}
                      >
                        <option value="normal">Normal (Unmasked)</option>
                        <option value="sensitive">Sensitive (Redact at AI)</option>
                        <option value="restricted">Restricted (Never send to AI)</option>
                        <option value="custom">Custom Policy</option>
                      </select>
                    </td>
                    <td className="py-3 px-4">
                      {getStatusBadge(col.status)}
                    </td>
                    <td className="py-3 px-4 text-slate-500 max-w-xs truncate" title={col.explanation}>
                      {col.explanation || "Standard schema column."}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Audit Log Modal / Drawer */}
      {showAuditModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm animate-fade-in">
          <div className="bg-white rounded-2xl max-w-3xl w-full max-h-[80vh] flex flex-col shadow-2xl border border-slate-200 overflow-hidden">
            <div className="p-4 border-b border-slate-200 flex items-center justify-between bg-slate-50">
              <div className="flex items-center gap-2">
                <Activity className="w-5 h-5 text-emerald-600" />
                <h3 className="font-bold text-slate-900 text-sm">Privacy Activity & Boundary Audit Trail</h3>
              </div>
              <button
                onClick={() => setShowAuditModal(false)}
                className="text-slate-400 hover:text-slate-600 text-lg leading-none"
              >
                &times;
              </button>
            </div>

            <div className="p-4 overflow-y-auto flex-1 divide-y divide-slate-100">
              {auditLogs.length === 0 ? (
                <div className="text-center py-8 text-slate-400 text-xs">
                  No privacy audit records found.
                </div>
              ) : (
                auditLogs.map((log) => (
                  <div key={log.id} className="py-2.5 flex items-start justify-between gap-4 text-xs">
                    <div className="space-y-0.5">
                      <div className="flex items-center gap-2">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase tracking-wider ${
                          log.event_type === "dataset_scan"
                            ? "bg-blue-100 text-blue-800"
                            : log.event_type === "policy_change"
                            ? "bg-purple-100 text-purple-800"
                            : log.event_type === "ai_boundary_redaction"
                            ? "bg-amber-100 text-amber-800"
                            : "bg-rose-100 text-rose-800"
                        }`}>
                          {log.event_type.replace(/_/g, " ")}
                        </span>
                        <span className="text-slate-400 text-[11px]">
                          {new Date(log.timestamp).toLocaleString()}
                        </span>
                      </div>
                      <p className="text-slate-700 font-mono text-[11px] mt-0.5">
                        {typeof log.details === "object" ? JSON.stringify(log.details) : log.details}
                      </p>
                    </div>
                  </div>
                ))
              )}
            </div>

            <div className="p-3 bg-slate-50 border-t border-slate-200 flex justify-end">
              <button
                onClick={() => setShowAuditModal(false)}
                className="px-4 py-1.5 text-xs font-semibold rounded-xl bg-slate-200 hover:bg-slate-300 text-slate-800 transition-all"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
