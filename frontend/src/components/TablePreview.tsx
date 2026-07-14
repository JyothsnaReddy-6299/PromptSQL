import { useState } from "react";
import { Search, ChevronLeft, ChevronRight, Download } from "lucide-react";
import { cleanUpdateCell } from "../services/api";

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

  const handleExportCSV = () => {
    if (records.length === 0) return;
    
    const headers = columns.join(",");
    const rows = records.map((row) =>
      columns
        .map((col) => {
          const val = row[col];
          const valStr = val === null || val === undefined ? "" : String(val);
          if (valStr.includes(",") || valStr.includes('"') || valStr.includes("\n")) {
            return `"${valStr.replace(/"/g, '""')}"`;
          }
          return valStr;
        })
        .join(",")
    );

    const csvContent = "data:text/csv;charset=utf-8," + [headers, ...rows].join("\n");
    const encodedUri = encodeURI(csvContent);
    const link = document.createElement("a");
    link.setAttribute("href", encodedUri);
    link.setAttribute("download", "raw_dataset_preview.csv");
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  return (
    <div id="preview" className="bg-[#111113] border border-white/[0.06] rounded-2xl p-5 shadow-2xl shadow-black/10">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 mb-5">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            Dataset Explorer
          </h2>
          <p className="text-zinc-550 text-[10px] font-medium mt-0.5">
            Showing first {records.length} records in active MySQL table
          </p>
        </div>

        {/* Tools */}
        <div className="flex flex-wrap items-center gap-2.5">
          {/* Search bar */}
          <div className="relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-zinc-500" size={13} />
            <input
              type="text"
              placeholder="Search records..."
              value={searchTerm}
              onChange={(e) => {
                onSearchChange(e.target.value);
                setCurrentPage(1);
              }}
              className="bg-white/[0.03] border border-white/[0.08] rounded-xl pl-8 pr-3 py-1.5 text-xs focus:outline-none focus:border-indigo-500 w-full sm:w-52 focus:bg-[#18181B] transition-all text-white font-medium placeholder-zinc-650"
            />
          </div>

          <button
            onClick={handleExportCSV}
            disabled={records.length === 0}
            className="flex items-center gap-1.5 border border-white/[0.08] hover:border-indigo-500/30 hover:bg-indigo-500/10 px-3.5 py-1.5 rounded-xl text-zinc-300 font-semibold text-[10px] cursor-pointer disabled:opacity-40 transition duration-200"
          >
            <Download size={12} className="text-indigo-400" />
            <span>Export CSV</span>
          </button>
        </div>
      </div>

      {loading ? (
        <div className="h-48 flex items-center justify-center text-zinc-550">
          <div className="flex flex-col items-center gap-2">
            <div className="w-6 h-6 border-2 border-indigo-500 border-t-transparent rounded-full animate-spin" />
            <span className="text-xs font-medium text-zinc-500">Fetching preview...</span>
          </div>
        </div>
      ) : records.length === 0 ? (
        <div className="h-48 flex items-center justify-center text-zinc-500 border border-dashed border-white/[0.08] rounded-xl">
          <div className="text-center p-4">
            <p className="text-xs font-semibold text-zinc-350">No records found or table is empty.</p>
            <p className="text-[10px] text-zinc-500 mt-0.5">Upload a dataset file to preview data.</p>
          </div>
        </div>
      ) : (
        <div>
          {/* Table Container */}
          <div className="overflow-x-auto border border-white/[0.06] rounded-xl max-h-[350px]">
            <table className="min-w-full border-collapse text-left text-[11px] text-zinc-300">
              <thead className="bg-[#0D0D0F] sticky top-0 border-b border-white/[0.06] z-10">
                <tr>
                  {columns.map((col) => (
                    <th
                      key={col}
                      onClick={() => handleHeaderClick(col)}
                      className="px-3.5 py-3 font-bold text-zinc-400 bg-[#0D0D0F] select-none whitespace-nowrap text-[10px] uppercase border-r border-white/[0.04] last:border-0 cursor-pointer hover:bg-white/[0.04] hover:text-white transition-all duration-200"
                    >
                      <span className="flex items-center gap-1.5">
                        <span>{col}</span>
                        {sortCol === col && (
                          <span className="text-[8px] text-indigo-400 font-bold font-mono">
                            {sortDir === "ASC" ? "▲" : "▼"}
                          </span>
                        )}
                      </span>
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody className="divide-y divide-white/[0.04] bg-[#111113]">
                {paginatedRecords.map((row, rowIdx) => (
                  <tr key={rowIdx} className="hover:bg-white/[0.02] transition">
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
                          className={`px-3.5 py-2.5 border-r border-white/[0.04] last:border-0 font-medium text-zinc-300 max-w-xs truncate cursor-pointer hover:bg-white/[0.03] ${isEditing ? "p-1" : ""}`}
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
                              className="w-full bg-[#18181B] border border-indigo-500 rounded px-2 py-1 text-xs text-white font-medium focus:outline-none"
                            />
                          ) : row[col] === null || row[col] === undefined ? (
                            <span className="text-zinc-500 font-mono text-[9px] italic bg-white/[0.02] px-1.5 py-0.5 rounded border border-white/[0.06]">null</span>
                          ) : (
                            String(row[col])
                          )}
                        </td>
                      );
                    })}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Footer Controls */}
          <div className="mt-4 flex flex-col sm:flex-row items-center justify-between gap-3 text-[10px]">
            <span className="text-zinc-500 font-medium">
              Showing {startIndex + 1} to {Math.min(startIndex + itemsPerPage, totalItems)} of {totalItems} entries
              {searchTerm && " (filtered)"}
            </span>

            <div className="flex items-center gap-3">
              <div className="flex items-center gap-1.5 text-zinc-500 font-medium">
                <span>Show</span>
                <select
                  value={itemsPerPage}
                  onChange={(e) => {
                    setItemsPerPage(Number(e.target.value));
                    setCurrentPage(1);
                  }}
                  className="bg-[#18181B] border border-white/[0.08] rounded-md px-1.5 py-0.5 focus:outline-none focus:border-indigo-500 text-zinc-300 font-semibold text-[10px]"
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
                  disabled={currentPage === 1}
                  className="p-1 border border-white/[0.08] rounded-md text-zinc-400 hover:bg-white/[0.05] hover:text-white disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
                >
                  <ChevronLeft size={12} />
                </button>
                <span className="font-semibold px-2.5 flex items-center border border-white/[0.08] rounded-md bg-[#18181B] text-zinc-300">
                  Page {currentPage} of {totalPages || 1}
                </span>
                <button
                  onClick={() => setCurrentPage((p) => Math.min(p + 1, totalPages))}
                  disabled={currentPage === totalPages || totalPages === 0}
                  className="p-1 border border-white/[0.08] rounded-md text-zinc-400 hover:bg-white/[0.05] hover:text-white disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
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
