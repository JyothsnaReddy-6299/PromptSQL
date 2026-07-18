import { useState, useEffect } from "react";
import { 
  FileText, 
  Trash2, 
  Edit3, 
  Eye, 
  Download, 
  Calendar, 
  Database,
  Loader2,
  X,
  FileDown
} from "lucide-react";
import { 
  getReports, 
  getReportDetail, 
  renameReport, 
  deleteReport, 
  downloadReportFile 
} from "../services/api";

export default function ReportsManager() {
  const [reports, setReports] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  // Detailed view modal state
  const [selectedReportId, setSelectedReportId] = useState<number | null>(null);
  const [reportDetail, setReportDetail] = useState<any>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Rename modal state
  const [renameId, setRenameId] = useState<number | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const [renaming, setRenaming] = useState(false);

  // Export dropdown state (per report ID)
  const [exportMenuId, setExportMenuId] = useState<number | null>(null);

  const loadReports = async () => {
    try {
      setLoading(true);
      setError("");
      const data = await getReports();
      setReports(data);
    } catch (err: any) {
      setError(err.message || "Failed to load saved reports");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadReports();
  }, []);

  const handleOpenDetail = async (id: number) => {
    try {
      setSelectedReportId(id);
      setLoadingDetail(true);
      const detail = await getReportDetail(id);
      setReportDetail(detail);
    } catch (err: any) {
      alert("Failed loading report details: " + err.message);
      setSelectedReportId(null);
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleRename = async () => {
    if (!renameId || !newTitle.trim()) return;
    try {
      setRenaming(true);
      await renameReport(renameId, newTitle.trim());
      setRenameId(null);
      setNewTitle("");
      loadReports();
    } catch (err: any) {
      alert("Failed renaming report: " + err.message);
    } finally {
      setRenaming(false);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Are you sure you want to delete this saved report?")) return;
    try {
      await deleteReport(id);
      loadReports();
      if (selectedReportId === id) {
        setSelectedReportId(null);
        setReportDetail(null);
      }
    } catch (err: any) {
      alert("Failed deleting report: " + err.message);
    }
  };

  const handleExport = async (id: number, format: "pdf" | "excel" | "csv", title: string) => {
    try {
      await downloadReportFile(id, format, title);
      setExportMenuId(null);
    } catch (err: any) {
      alert("Export failed: " + err.message);
    }
  };

  return (
    <div id="reports" className="bg-[#111113] border border-white/[0.06] rounded-2xl p-5 shadow-2xl shadow-black/10">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <FileText className="text-terracotta-500" size={18} />
            <span>Saved Reports</span>
          </h2>
          <p className="text-zinc-400 text-[10px] mt-0.5 font-semibold">
            Manage, review, and re-export your saved query reports
          </p>
        </div>
        <button
          onClick={loadReports}
          className="text-xs font-bold text-terracotta-500 hover:text-terracotta-600 transition cursor-pointer"
        >
          Refresh List
        </button>
      </div>

      {loading ? (
        <div className="h-48 flex items-center justify-center">
          <Loader2 className="animate-spin text-terracotta-500" size={24} />
        </div>
      ) : error ? (
        <div className="h-48 flex items-center justify-center border border-dashed border-red-500/20 bg-red-500/[0.06] text-red-400 rounded-xl p-4 text-xs font-semibold">
          {error}
        </div>
      ) : reports.length === 0 ? (
        <div className="h-48 flex flex-col items-center justify-center text-zinc-500 border border-dashed border-white/[0.08] rounded-xl p-4">
          <FileText className="text-zinc-600 mb-1" size={24} />
          <p className="text-xs font-bold text-zinc-300">No reports saved yet.</p>
          <p className="text-[10px] text-zinc-500 mt-0.5">Click the "Save as Report" button inside the AI Assistant chat after running queries.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {reports.map((report) => (
            <div
              key={report.id}
              className="bg-[#18181B] border border-white/[0.06] rounded-xl p-4 shadow-sm hover:shadow hover:border-indigo-500/30 transition-all flex flex-col justify-between relative"
            >
              <div>
                <div className="flex justify-between items-start gap-2 mb-2">
                  <h3 className="text-sm font-bold text-white truncate max-w-[80%]" title={report.title}>
                    {report.title}
                  </h3>
                  {/* Export Trigger */}
                  <div className="relative">
                    <button
                      onClick={() => setExportMenuId(exportMenuId === report.id ? null : report.id)}
                      className="p-1 hover:bg-white/[0.04] rounded transition text-zinc-400 hover:text-white cursor-pointer"
                      title="Export report"
                    >
                      <Download size={14} className="text-terracotta-500" />
                    </button>
                    {exportMenuId === report.id && (
                      <div className="absolute right-0 mt-1 bg-[#18181B] border border-white/[0.08] rounded-lg shadow-lg py-1.5 w-24 z-20 text-[10px] font-bold">
                        <button
                          onClick={() => handleExport(report.id, "pdf", report.title)}
                          className="w-full text-left px-3 py-1 hover:bg-white/[0.04] flex items-center gap-1.5 cursor-pointer text-zinc-300 hover:text-white"
                        >
                          PDF Format
                        </button>
                        <button
                          onClick={() => handleExport(report.id, "excel", report.title)}
                          className="w-full text-left px-3 py-1 hover:bg-white/[0.04] flex items-center gap-1.5 cursor-pointer text-zinc-300 hover:text-white"
                        >
                          Excel File
                        </button>
                        <button
                          onClick={() => handleExport(report.id, "csv", report.title)}
                          className="w-full text-left px-3 py-1 hover:bg-white/[0.04] flex items-center gap-1.5 cursor-pointer text-zinc-300 hover:text-white"
                        >
                          CSV Sheet
                        </button>
                      </div>
                    )}
                  </div>
                </div>

                <p className="text-xs text-zinc-300 font-semibold italic bg-[#09090B] border border-white/[0.06] rounded-lg p-2.5 mb-3 line-clamp-2">
                  "{report.question}"
                </p>

                <div className="space-y-1.5 text-[10px] text-zinc-400 font-semibold mb-4">
                  <div className="flex items-center gap-1">
                    <Database size={12} className="text-zinc-500" />
                    <span className="truncate">{report.table_name.split("_usr_")[0]}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <Calendar size={12} className="text-zinc-500" />
                    <span>{new Date(report.timestamp).toLocaleString()}</span>
                  </div>
                </div>
              </div>

              {/* Action bar */}
              <div className="border-t border-white/[0.06] pt-3 mt-auto flex justify-between gap-2">
                <button
                  onClick={() => handleOpenDetail(report.id)}
                  className="flex items-center gap-1 bg-white/[0.04] border border-white/[0.08] hover:bg-indigo-500/10 hover:border-indigo-500/30 px-2.5 py-1.5 rounded-lg text-[10px] font-bold text-zinc-300 hover:text-white transition cursor-pointer"
                >
                  <Eye size={12} />
                  <span>View Details</span>
                </button>

                <div className="flex gap-1">
                  <button
                    onClick={() => {
                      setRenameId(report.id);
                      setNewTitle(report.title);
                    }}
                    className="p-1.5 border border-white/[0.08] hover:bg-white/[0.04] rounded-lg text-zinc-400 hover:text-white cursor-pointer transition"
                    title="Rename report"
                  >
                    <Edit3 size={12} />
                  </button>
                  <button
                    onClick={() => handleDelete(report.id)}
                    className="p-1.5 border border-white/[0.08] hover:bg-red-500/10 hover:border-red-500/30 rounded-lg text-zinc-400 hover:text-red-400 cursor-pointer transition"
                    title="Delete report"
                  >
                    <Trash2 size={12} />
                  </button>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Rename Modal overlay */}
      {renameId !== null && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[#111113] border border-white/[0.08] rounded-xl max-w-sm w-full p-5 shadow-2xl space-y-4">
            <h3 className="text-sm font-bold text-white">Rename Report</h3>
            <input
              type="text"
              value={newTitle}
              onChange={(e) => setNewTitle(e.target.value)}
              placeholder="Enter new report title..."
              className="w-full bg-[#09090B] border border-white/[0.06] rounded-lg px-3 py-2 text-xs focus:outline-none focus:border-indigo-500 focus:bg-[#09090B] text-white font-bold"
            />
            <div className="flex justify-end gap-2.5">
              <button
                onClick={() => {
                  setRenameId(null);
                  setNewTitle("");
                }}
                disabled={renaming}
                className="px-3 py-1.5 border border-white/[0.08] rounded-lg text-xs font-bold text-zinc-400 hover:bg-white/[0.04] cursor-pointer disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={handleRename}
                disabled={renaming || !newTitle.trim()}
                className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-500 text-white rounded-lg text-xs font-bold shadow-sm shadow-indigo-500/10 cursor-pointer disabled:opacity-50 flex items-center gap-1"
              >
                {renaming && <Loader2 size={12} className="animate-spin" />}
                <span>Save Title</span>
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Details View Modal overlay */}
      {selectedReportId !== null && (
        <div className="fixed inset-0 bg-black/60 backdrop-blur-xs flex items-center justify-center z-50 p-4">
          <div className="bg-[#111113] border border-white/[0.08] rounded-2xl max-w-3xl w-full max-h-[85vh] flex flex-col shadow-2xl overflow-hidden animate-fade-in">
            {/* Header */}
            <div className="bg-[#18181B]/80 border-b border-white/[0.06] px-5 py-3.5 flex justify-between items-center">
              <div className="flex items-center gap-2">
                <FileText className="text-terracotta-500" size={18} />
                <h3 className="text-sm font-bold text-white">
                  {loadingDetail ? "Loading Report..." : reportDetail?.title}
                </h3>
              </div>
              <button
                onClick={() => {
                  setSelectedReportId(null);
                  setReportDetail(null);
                }}
                className="p-1 hover:bg-white/[0.04] rounded-lg text-zinc-400 hover:text-white cursor-pointer transition"
              >
                <X size={16} />
              </button>
            </div>

            {/* Scrollable details content */}
            {loadingDetail ? (
              <div className="h-96 flex items-center justify-center">
                <Loader2 className="animate-spin text-terracotta-500" size={28} />
              </div>
            ) : reportDetail ? (
              <div className="flex-1 overflow-y-auto p-5 space-y-4 text-left text-xs">
                {/* Meta details */}
                <div className="grid grid-cols-2 gap-3 bg-[#09090B] border border-white/[0.06] rounded-xl p-3 font-semibold text-[10px] text-zinc-400">
                  <div>
                    <span className="text-zinc-500 block uppercase tracking-wider">Source Table</span>
                    <span className="text-white text-xs font-bold">{reportDetail.table_name.split("_usr_")[0]}</span>
                  </div>
                  <div>
                    <span className="text-zinc-500 block uppercase tracking-wider">Saved On</span>
                    <span className="text-white text-xs font-bold">
                      {new Date(reportDetail.timestamp).toLocaleString()}
                    </span>
                  </div>
                </div>

                {/* Question */}
                <div>
                  <h4 className="font-bold text-white mb-1.5 uppercase text-[9px] tracking-wide text-terracotta-500">
                    Query Question
                  </h4>
                  <div className="p-3 bg-[#09090B] border border-white/[0.06] rounded-xl text-zinc-200 font-bold leading-relaxed">
                    {reportDetail.question}
                  </div>
                </div>

                {/* SQL Code */}
                <div>
                  <h4 className="font-bold text-white mb-1.5 uppercase text-[9px] tracking-wide text-terracotta-500">
                    Generated SQL
                  </h4>
                  <pre className="p-3 bg-[#09090B] text-indigo-400 rounded-xl font-mono text-[10.5px] overflow-x-auto whitespace-pre border border-white/[0.06]">
                    <code>{reportDetail.generated_sql}</code>
                  </pre>
                </div>

                {/* Summary */}
                <div>
                  <h4 className="font-bold text-white mb-1.5 uppercase text-[9px] tracking-wide text-terracotta-500">
                    AI Summary Explanation
                  </h4>
                  <div className="p-3 bg-[#09090B] border border-white/[0.06] rounded-xl text-zinc-200 font-semibold leading-relaxed whitespace-pre-wrap">
                    {reportDetail.summary}
                  </div>
                </div>

                {/* Saved Records Grid inside modal */}
                <div>
                  <h4 className="font-bold text-white mb-1.5 uppercase text-[9px] tracking-wide text-terracotta-500">
                    Saved Result Data ({reportDetail.records?.length || 0} rows)
                  </h4>
                  
                  {reportDetail.records && reportDetail.records.length > 0 ? (
                    <DetailRecordsTable records={reportDetail.records} />
                  ) : (
                    <div className="p-3 border border-dashed border-white/[0.08] rounded-xl text-center text-zinc-500">
                      No records saved.
                    </div>
                  )}
                </div>
              </div>
            ) : null}

            {/* Footer containing quick export options */}
            {!loadingDetail && reportDetail && (
              <div className="bg-[#18181B] border-t border-white/[0.06] px-5 py-3 flex flex-wrap justify-between items-center gap-3">
                <span className="text-[10px] font-bold text-zinc-400">
                  Quick Export File
                </span>
                <div className="flex gap-2 text-[10px] font-bold">
                  <button
                    onClick={() => handleExport(reportDetail.id, "pdf", reportDetail.title)}
                    className="flex items-center gap-1.5 border border-white/[0.08] hover:border-indigo-500/30 hover:bg-white/[0.04] bg-[#09090B] px-3 py-1.5 rounded-lg text-zinc-300 hover:text-white transition cursor-pointer"
                  >
                    <FileDown size={12} className="text-terracotta-500" /> PDF Report
                  </button>
                  <button
                    onClick={() => handleExport(reportDetail.id, "excel", reportDetail.title)}
                    className="flex items-center gap-1.5 border border-white/[0.08] hover:border-indigo-500/30 hover:bg-white/[0.04] bg-[#09090B] px-3 py-1.5 rounded-lg text-zinc-300 hover:text-white transition cursor-pointer"
                  >
                    <FileDown size={12} className="text-terracotta-500" /> Excel Sheet
                  </button>
                  <button
                    onClick={() => handleExport(reportDetail.id, "csv", reportDetail.title)}
                    className="flex items-center gap-1.5 border border-white/[0.08] hover:border-indigo-500/30 hover:bg-white/[0.04] bg-[#09090B] px-3 py-1.5 rounded-lg text-zinc-300 hover:text-white transition cursor-pointer"
                  >
                    <FileDown size={12} className="text-terracotta-500" /> CSV Data
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

// Inner Component to paginate records inside details modal
function DetailRecordsTable({ records }: { records: Record<string, any>[] }) {
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 5;
  const columns = Object.keys(records[0] || {});

  const totalPages = Math.ceil(records.length / itemsPerPage);
  const start = (currentPage - 1) * itemsPerPage;
  const paginated = records.slice(start, start + itemsPerPage);

  return (
    <div className="space-y-2 border border-white/[0.06] rounded-xl p-3 bg-[#09090B]">
      <div className="overflow-x-auto border border-white/[0.06] rounded-lg">
        <table className="min-w-full text-[10px] text-zinc-300">
          <thead className="bg-[#18181B] border-b border-white/[0.06]">
            <tr>
              {columns.map(col => (
                <th key={col} className="px-2.5 py-1.5 font-bold text-zinc-300 text-left uppercase whitespace-nowrap text-[9px]">
                  {col}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/[0.04] bg-[#111113]">
            {paginated.map((row, rIdx) => (
              <tr key={rIdx} className="hover:bg-white/[0.02] transition">
                {columns.map(col => (
                  <td key={col} className="px-2.5 py-1.5 text-zinc-200 font-semibold truncate max-w-[120px]">
                    {row[col] === null ? "null" : formatDateValue(row[col])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex justify-between items-center text-[9px] text-zinc-400 font-bold pt-1">
        <span>Showing {start + 1}-{Math.min(start + itemsPerPage, records.length)} of {records.length}</span>
        {totalPages > 1 && (
          <div className="flex gap-1">
            <button
              onClick={() => setCurrentPage(p => Math.max(p - 1, 1))}
              disabled={currentPage === 1}
              className="p-0.5 border border-white/[0.08] rounded hover:bg-white/[0.04] text-zinc-400 hover:text-white disabled:opacity-40"
            >
              &lt;
            </button>
            <span className="px-1.5 flex items-center">
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage(p => Math.min(p + 1, totalPages))}
              disabled={currentPage === totalPages}
              className="p-0.5 border border-white/[0.08] rounded hover:bg-white/[0.04] text-zinc-400 hover:text-white disabled:opacity-40"
            >
              &gt;
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

function formatDateValue(val: any): string {
  if (val === null || val === undefined) return "";
  const s = String(val);
  if (/^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}:\d{2})?/.test(s)) {
    if (s.includes("00:00:00") || s.includes("T00:00:00")) {
      return s.split(/[T ]/)[0];
    }
  }
  return s;
}
