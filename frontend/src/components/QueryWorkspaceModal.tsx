import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, Upload, Database, FileSpreadsheet, Plus, Trash2, ArrowLeft, Loader2, PlusCircle } from "lucide-react";
import { createTable } from "../services/api";

interface QueryWorkspaceModalProps {
  onClose: () => void;
}

interface ColumnDef {
  name: string;
  type: string;
}

export default function QueryWorkspaceModal({ onClose }: QueryWorkspaceModalProps) {
  const navigate = useNavigate();
  const [view, setView] = useState<"options" | "create">("options");
  
  // Table creation form states
  const [tableName, setTableName] = useState("");
  const [columns, setColumns] = useState<ColumnDef[]>([
    { name: "title", type: "VARCHAR(255)" },
    { name: "amount", type: "DOUBLE" }
  ]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUseExisting = () => {
    onClose();
    navigate("/dashboard");
  };

  const handleUploadNew = () => {
    onClose();
    navigate("/upload");
  };

  const handleAddColumn = () => {
    setColumns([...columns, { name: `column_${columns.length + 1}`, type: "VARCHAR(255)" }]);
  };

  const handleRemoveColumn = (index: number) => {
    if (columns.length <= 1) return;
    setColumns(columns.filter((_, idx) => idx !== index));
  };

  const handleColumnChange = (index: number, field: keyof ColumnDef, val: string) => {
    setColumns(
      columns.map((col, idx) => (idx === index ? { ...col, [field]: val } : col))
    );
  };

  const handleCreateTable = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!tableName.trim()) {
      setError("Please specify a table name.");
      return;
    }
    
    // Validate column names are not empty
    const invalidCols = columns.some(c => !c.name.trim());
    if (invalidCols) {
      setError("All columns must have a valid name.");
      return;
    }

    try {
      setCreating(true);
      setError(null);
      const res = await createTable(tableName.trim(), columns);
      if (res.success && res.table_name) {
        // Set local storage and session active dataset
        const friendlyName = res.table_name.split("_usr_")[0];
        sessionStorage.setItem("dataset", JSON.stringify({
          table_name: res.table_name,
          filename: friendlyName,
          rows: 0,
          columns: columns.length + 1, // include id column
          missing_values: 0,
          detected_types: {}
        }));
        onClose();
        navigate("/dashboard");
      } else {
        setError(res.error || "Failed to create table.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to create table. Table name might be taken.");
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop blur */}
      <div 
        onClick={onClose}
        className="absolute inset-0 bg-[#241C20]/60 backdrop-blur-md transition-opacity duration-300"
      />

      {/* Modal Container */}
      <div className={`relative bg-[#FFFDFC] border border-[#E8DED3] rounded-3xl p-7 w-full shadow-2xl z-10 overflow-hidden transition-all duration-300 ${
        view === "create" ? "max-w-lg" : "max-w-sm"
      } animate-in fade-in zoom-in-95 duration-200`}>
        
        {/* Glow decoration */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[300px] h-[150px] bg-[#5A2F59]/5 rounded-full blur-[40px] pointer-events-none -z-10" />

        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-2">
            {view === "create" && (
              <button 
                onClick={() => { setView("options"); setError(null); }}
                className="w-7 h-7 bg-[#F7F2EC] hover:bg-[#E8DED3] rounded-full flex items-center justify-center text-[#6F6A67] hover:text-[#241C20] cursor-pointer mr-1 transition-colors"
                title="Go Back"
              >
                <ArrowLeft size={13} />
              </button>
            )}
            <div className="w-8 h-8 bg-[#5A2F59]/8 rounded-xl flex items-center justify-center border border-[#5A2F59]/15">
              <Database size={15} className="text-[#5A2F59]" />
            </div>
            <h3 className="text-base font-bold text-[#241C20] tracking-tight">
              {view === "create" ? "Create Custom Table" : "Query Workspace"}
            </h3>
          </div>
          <button 
            onClick={onClose}
            className="w-7 h-7 bg-[#F7F2EC] hover:bg-[#E8DED3] rounded-full flex items-center justify-center text-[#6F6A67] hover:text-[#241C20] cursor-pointer transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        {view === "options" ? (
          <>
            <p className="text-xs text-[#6F6A67] leading-relaxed mb-5">
              Would you like to continue querying your active dataset, upload a new spreadsheet file, or manually create a clean custom table?
            </p>

            {/* Options */}
            <div className="space-y-2.5">
              {/* Use active dataset option */}
              <button
                onClick={handleUseExisting}
                className="w-full p-3.5 rounded-2xl bg-[#FFFDFC] border border-[#E8DED3] hover:border-[#5A2F59]/30 hover:bg-[#5A2F59]/3 flex items-center gap-4 transition-all duration-200 text-left cursor-pointer group shadow-sm"
              >
                <div className="w-9 h-9 rounded-xl bg-[#5A2F59]/8 border border-[#5A2F59]/15 flex items-center justify-center text-[#5A2F59] shrink-0 group-hover:scale-105 transition-transform">
                  <FileSpreadsheet size={16} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-[#241C20] group-hover:text-[#5A2F59] transition-colors">
                    Use Active Dataset
                  </h4>
                  <p className="text-[9px] text-[#6F6A67] mt-0.5 leading-none">
                    Resume analyzing your loaded data
                  </p>
                </div>
              </button>

              {/* Upload new dataset option */}
              <button
                onClick={handleUploadNew}
                className="w-full p-3.5 rounded-2xl bg-[#FFFDFC] border border-[#E8DED3] hover:border-[#5A2F59]/30 hover:bg-[#5A2F59]/3 flex items-center gap-4 transition-all duration-200 text-left cursor-pointer group shadow-sm"
              >
                <div className="w-9 h-9 rounded-xl bg-[#5A2F59]/8 border border-[#5A2F59]/15 flex items-center justify-center text-[#5A2F59] shrink-0 group-hover:scale-105 transition-transform">
                  <Upload size={16} />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-[#241C20] group-hover:text-[#5A2F59] transition-colors">
                    Upload New Dataset
                  </h4>
                  <p className="text-[9px] text-[#6F6A67] mt-0.5 leading-none">
                    Import a CSV or Excel file
                  </p>
                </div>
              </button>

              {/* Create new table option */}
              <button
                onClick={() => setView("create")}
                className="w-full p-3.5 rounded-2xl bg-[#FFFDFC] border border-[#E8DED3] hover:border-[#5A2F59]/30 hover:bg-[#5A2F59]/3 flex items-center gap-4 transition-all duration-200 text-left cursor-pointer group shadow-sm"
              >
                <div className="w-9 h-9 rounded-xl bg-[#BDA37A]/15 border border-[#BDA37A]/30 flex items-center justify-center text-[#BDA37A] shrink-0 group-hover:scale-105 transition-transform">
                  <PlusCircle size={16} className="text-[#BDA37A]" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-[#241C20] group-hover:text-[#5A2F59] transition-colors">
                    Create Custom Table
                  </h4>
                  <p className="text-[9px] text-[#6F6A67] mt-0.5 leading-none">
                    Design custom database columns
                  </p>
                </div>
              </button>
            </div>
          </>
        ) : (
          /* Create Table Form Subview */
          <form onSubmit={handleCreateTable} className="space-y-4 text-left">
            {error && (
              <div className="p-3 bg-red-500/5 border border-red-500/10 rounded-xl text-red-700 text-[11px] leading-tight">
                {error}
              </div>
            )}

            {/* Table Name Input */}
            <div>
              <label className="block text-[10px] font-bold text-[#BDA37A] uppercase tracking-wider mb-1.5">
                Table Name
              </label>
              <input
                type="text"
                required
                value={tableName}
                onChange={(e) => setTableName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
                placeholder="e.g. quarterly_targets"
                className="w-full px-3.5 py-2.5 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#5A2F59]/40 rounded-xl text-[#241C20] placeholder-[#B0A79E] text-xs focus:outline-none transition-all"
              />
              <span className="text-[9px] text-[#6F6A67] mt-1 block">
                Lowercase letters, numbers, and underscores only.
              </span>
            </div>

            {/* Columns List Header */}
            <div>
              <div className="flex justify-between items-center mb-2">
                <label className="block text-[10px] font-bold text-[#BDA37A] uppercase tracking-wider">
                  Columns Configuration
                </label>
                <span className="text-[9px] text-[#6F6A67] italic font-semibold">
                  (Auto-includes primary key 'id' INT)
                </span>
              </div>

              {/* Scrollable Column Configuration items */}
              <div className="max-h-52 overflow-y-auto space-y-2 pr-1 custom-scrollbar">
                {columns.map((col, index) => (
                  <div key={index} className="flex gap-2 items-center">
                    <input
                      type="text"
                      required
                      value={col.name}
                      onChange={(e) => handleColumnChange(index, "name", e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
                      placeholder="column_name"
                      className="flex-1 px-3 py-2 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl text-[#241C20] placeholder-[#B0A79E] text-xs focus:outline-none focus:border-[#5A2F59]/40 transition-all"
                    />
                    <select
                      value={col.type}
                      onChange={(e) => handleColumnChange(index, "type", e.target.value)}
                      className="w-28 px-2 py-2 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl text-[#241C20] text-xs focus:outline-none focus:border-[#5A2F59]/40 cursor-pointer"
                    >
                      <option value="VARCHAR(255)">TEXT (Varchar)</option>
                      <option value="INT">INTEGER</option>
                      <option value="DOUBLE">NUMBER (Double)</option>
                      <option value="DATE">DATE</option>
                      <option value="TEXT">LONG TEXT</option>
                    </select>
                    <button
                      type="button"
                      onClick={() => handleRemoveColumn(index)}
                      disabled={columns.length <= 1}
                      className="w-8 h-8 bg-red-500/5 hover:bg-red-500/10 text-red-600 rounded-xl flex items-center justify-center shrink-0 border border-red-500/10 hover:border-red-500/20 cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                    >
                      <Trash2 size={13} />
                    </button>
                  </div>
                ))}
              </div>

              {/* Add Column Action */}
              <button
                type="button"
                onClick={handleAddColumn}
                className="mt-3.5 flex items-center gap-1.5 text-xs text-[#5A2F59] hover:text-[#4A2549] font-bold cursor-pointer"
              >
                <Plus size={14} />
                <span>Add Column</span>
              </button>
            </div>

            {/* Create Table submit action */}
            <button
              type="submit"
              disabled={creating}
              className="mt-5 w-full bg-[#5A2F59] hover:bg-[#4A2549] text-white py-3.5 rounded-xl font-semibold hover:scale-[1.01] active:scale-[0.99] transition-all duration-200 shadow-md shadow-[#5A2F59]/10 cursor-pointer flex justify-center items-center gap-2 text-xs disabled:opacity-60 disabled:pointer-events-none"
            >
              {creating ? (
                <>
                  <Loader2 size={14} className="animate-spin" />
                  <span>Creating Table...</span>
                </>
              ) : (
                <>
                  <Database size={14} />
                  <span>Build Custom Table</span>
                </>
              )}
            </button>
          </form>
        )}

      </div>
    </div>
  );
}
