import { useState } from "react";
import { Search, ChevronLeft, ChevronRight, Download, Loader2 } from "lucide-react";
import { cleanUpdateCell, downloadRawCSV, downloadRawExcel } from "../services/api";

interface Props {
  columns: string[];
  records: Record<string, any>[];
  loading?: boolean;
  searchTerm: string;
  onSearchChange: (val: string) => void;
  sortCol: string;
  sortDir: string;
  onSortChange: (col: string, dir: string) => void;
  onRefresh?: () => void;
}

export default function TablePreview({
  columns = [],
  records = [],
  loading = false,
  searchTerm,
  onSearchChange,
  sortCol = "",
  sortDir = "ASC",
  onSortChange,
  onRefresh
}: Props) {
  const [currentPage, setCurrentPage] = useState(1);
  const [itemsPerPage, setItemsPerPage] = useState(10);
  const [editingCell, setEditingCell] = useState<{ globalRowIdx: number; colName: string } | null>(null);
  const [editValue, setEditValue] = useState("");
  const [exportingCSV, setExportingCSV] = useState(false);
  const [exportingExcel, setExportingExcel] = useState(false);

  const handleHeaderClick = (colName: string) => {
    if (sortCol === colName) {
      onSortChange(colName, sortDir === "ASC" ? "DESC" : "ASC");
    } else {
      onSortChange(colName, "ASC");
    }
  };

  const totalItems = records.length;
  const totalPages = Math.ceil(totalItems / itemsPerPage);
  const startIndex = (currentPage - 1) * itemsPerPage;
  const paginatedRecords = records.slice(startIndex, startIndex + itemsPerPage);

  const saveEdit = async (globalRowIdx: number, colName: string) => {
    if (!editingCell) return;
    const originalRowData = records[globalRowIdx];
    const originalValue = originalRowData[colName];
    const trimmedVal = editValue.trim();

    if (String(originalValue ?? "") === trimmedVal) {
      setEditingCell(null);
      return;
    }

    try {
      setEditingCell(null);
      const res = await cleanUpdateCell(colName, trimmedVal, originalRowData);
      if (res.success) {
        if (onRefresh) onRefresh();
      } else {
        alert(res.error || "Failed to update cell.");
      }
    } catch (e: any) {
      alert(e.message || "Error updating cell.");
    }
  };

  const handleExportCSV = async () => {
    try {
      setExportingCSV(true);
      await downloadRawCSV();
    } catch (e: any) {
      alert("CSV export failed: " + (e.message || e));
    } finally {
      setExportingCSV(false);
    }
  };

  const handleExportExcel = async () => {
    try {
      setExportingExcel(true);
      await downloadRawExcel();
    } catch (e: any) {
      alert("Excel export failed: " + (e.message || e));
    } finally {
      setExportingExcel(false);
    }
  };

  return (
    <div id="preview" className="bg-[#FFFDFC] border border-[#E8DED3] rounded-2xl p-5 shadow-sm shadow-[#5A2F59]/5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
        <div>
          <h2 className="text-base font-bold text-[#241C20] flex items-center gap-2">
            Dataset Explorer
          </h2>
          <p className="text-[10px] text-[#6F6A67] mt-0.5">
            Double click any cell to edit data inline.
          </p>
        </div>

        <div className="flex flex-wrap items-center gap-2 w-full sm:w-auto">
          {/* Local search input */}
          <div className="relative flex-1 sm:flex-none">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-[#B0A79E] w-3.5 h-3.5" />
            <input
              type="text"
              placeholder='Search text or "col:null"...'
              value={searchTerm}
              onChange={(e) => {
                onSearchChange(e.target.value);
                setCurrentPage(1);
              }}
              className="bg-[#F7F2EC] border border-[#E8DED3] rounded-xl pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:border-[#5A2F59] w-full sm:w-60 focus:bg-[#FFFDFC] transition-all text-[#241C20] font-medium placeholder-[#B0A79E]"
            />
          </div>

          <button
            onClick={handleExportCSV}
            disabled={records.length === 0 || exportingCSV || exportingExcel}
            className="flex items-center gap-1.5 border border-[#E8DED3] hover:border-[#5A2F59]/30 hover:bg-[#5A2F59]/5 px-3.5 py-1.5 rounded-xl text-[#6F6A67] hover:text-[#241C20] font-semibold text-[10px] cursor-pointer disabled:opacity-40 transition duration-200"
          >
            {exportingCSV ? (
              <Loader2 size={12} className="text-[#5A2F59] animate-spin" />
            ) : (
              <Download size={12} className="text-[#5A2F59]" />
            )}
            <span>Export CSV</span>
          </button>

          <button
            onClick={handleExportExcel}
            disabled={records.length === 0 || exportingCSV || exportingExcel}
            className="flex items-center gap-1.5 border border-[#E8DED3] hover:border-[#5A2F59]/30 hover:bg-[#5A2F59]/5 px-3.5 py-1.5 rounded-xl text-[#6F6A67] hover:text-[#241C20] font-semibold text-[10px] cursor-pointer disabled:opacity-40 transition duration-200"
          >
            {exportingExcel ? (
              <Loader2 size={12} className="text-[#5A2F59] animate-spin" />
            ) : (
              <Download size={12} className="text-[#5A2F59]" />
            )}
            <span>Export Excel</span>
          </button>
        </div>
      </div>

      {loading ? (
        <div className="h-48 flex items-center justify-center text-zinc-550">
          <div className="flex flex-col items-center gap-2">
            <div className="w-6 h-6 border-2 border-[#5A2F59] border-t-transparent rounded-full animate-spin" />
            <span className="text-xs font-semibold text-[#6F6A67]">Fetching preview...</span>
          </div>
        </div>
      ) : columns.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-zinc-500 border border-dashed border-[#E8DED3] rounded-xl bg-[#F7F2EC]/30">
          <div className="text-center p-4">
            <p className="text-xs font-bold text-[#6F6A67]">No active dataset loaded.</p>
            <p className="text-[10px] text-zinc-400 mt-0.5">Please upload a dataset or create a table to begin.</p>
          </div>
        </div>
      ) : (
        <div>
          {/* Table Container */}
          <div className="overflow-x-auto border border-[#E8DED3] rounded-xl max-h-[350px]">
            <table className="min-w-full border-collapse text-left text-[11px] text-[#241C20]">
              <thead className="bg-[#5A2F59]/6 sticky top-0 border-b border-[#E8DED3] z-10">
                <tr>
                  {columns.map((col) => (
                    <th
                      key={col}
                      onClick={() => handleHeaderClick(col)}
                      className="px-3.5 py-3 font-bold text-[#5A2F59] bg-[#F7F2EC] select-none whitespace-nowrap text-[10px] uppercase border-r border-[#E8DED3] last:border-0 cursor-pointer hover:bg-[#5A2F59]/8 transition-all duration-200"
                    >
                      <span className="flex items-center gap-1.5">
                        <span>{col}</span>
                        {sortCol === col && (
                          <span className="text-[8px] text-[#5A2F59] font-bold font-mono">
                            {sortDir === "ASC" ? "▲" : "▼"}
                          </span>
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E8DED3] bg-[#FFFDFC] border-t border-[#E8DED3]">
                {records.length === 0 ? (
                  <tr>
                    <td colSpan={columns.length} className="px-6 py-12 text-center text-xs font-semibold text-[#6F6A67]">
                      No records found. This table is currently empty. Use the chat box assistant below to insert records!
                    </td>
                  </tr>
                ) : (
                  paginatedRecords.map((row, rowIdx) => (
                    <tr key={rowIdx} className="hover:bg-[#5A2F59]/3 transition">
                      {columns.map((col) => {
                        const globalIdx = startIndex + rowIdx;
                        const isEditing = editingCell?.globalRowIdx === globalIdx && editingCell?.colName === col;
                        return (
                          <td
                            key={col}
                            onDoubleClick={() => {
                              setEditingCell({ globalRowIdx: globalIdx, colName: col });
                              setEditValue(row[col] === null || row[col] === undefined ? "" : String(row[col]));
                            }}
                            className={`px-3.5 py-2.5 border-r border-[#E8DED3]/60 last:border-0 font-medium text-[#241C20] max-w-xs truncate cursor-pointer hover:bg-[#5A2F59]/5 ${isEditing ? "p-1" : ""}`}
                            title={row[col] !== null ? String(row[col]) : "Double click to edit cell"}
                          >
                            {isEditing ? (
                              <input
                                type="text"
                                value={editValue}
                                onChange={(e) => setEditValue(e.target.value)}
                                onBlur={() => saveEdit(globalIdx, col)}
                                onKeyDown={(e) => {
                                  if (e.key === "Enter") saveEdit(globalIdx, col);
                                  if (e.key === "Escape") setEditingCell(null);
                                }}
                                autoFocus
                                className="w-full bg-[#FFFDFC] border border-[#5A2F59] rounded px-2 py-1 text-xs text-[#241C20] font-medium focus:outline-none focus:ring-1 focus:ring-[#5A2F59]"
                              />
                            ) : row[col] === null || row[col] === undefined ? (
                              <span className="text-[#5A2F59]/50 font-mono text-[9px] italic bg-[#5A2F59]/5 px-1.5 py-0.5 rounded border border-[#E8DED3]/40">null</span>
                            ) : (
                              formatDateValue(row[col])
                            )}
                          </td>
                        );
                      })}
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>

          {/* Footer Controls */}
          <div className="mt-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-[10px]">
            <span className="text-[#6F6A67] font-medium">
              Showing {totalItems === 0 ? 0 : startIndex + 1} to {Math.min(startIndex + itemsPerPage, totalItems)} of {totalItems} entries
              {searchTerm && " (filtered)"}
            </span>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-[#6F6A67] font-medium">
                <span>Show</span>
                <select
                  value={itemsPerPage}
                  onChange={(e) => {
                    setItemsPerPage(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="bg-[#F7F2EC] border border-[#E8DED3] rounded-md px-1.5 py-0.5 focus:outline-none focus:border-[#5A2F59] text-[#241C20] font-semibold text-[10px]"
                >
                  <option value={5}>5</option>
                  <option value={10}>10</option>
                  <option value={20}>20</option>
                  <option value={50}>50</option>
                </select>
                <span>rows</span>
              </div>

              <div className="flex gap-1.5">
                <button
                  onClick={() => setCurrentPage((p) => Math.max(p - 1, 1))}
                  disabled={currentPage === 1 || totalPages === 0}
                  className="p-1 border border-[#E8DED3] rounded-md text-[#6F6A67] hover:bg-[#5A2F59]/5 hover:text-[#241C20] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                >
                  <ChevronLeft size={12} />
                </button>
                <span className="font-semibold px-2.5 flex items-center border border-[#E8DED3] rounded-md bg-[#F7F2EC] text-[#241C20]">
                  Page {currentPage} of {totalPages || 1}
                </span>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
                  disabled={currentPage === totalPages || totalPages === 0}
                  className="p-1 border border-[#E8DED3] rounded-md text-[#6F6A67] hover:bg-[#5A2F59]/5 hover:text-[#241C20] disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                >
                  <ChevronRight size={12} />
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
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
