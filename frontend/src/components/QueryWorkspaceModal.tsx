import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { X, Upload, Database, FileSpreadsheet, Plus, Trash2, ArrowLeft, Loader2, PlusCircle, Sparkles, CheckCircle2, MessageSquarePlus } from "lucide-react";
import { createTable, generateTableSchema, getPreview, getDatasets, setActiveDataset } from "../services/api";

interface QueryWorkspaceModalProps {
  onClose: () => void;
  initialView?: "options" | "create";
}

interface ColumnDef {
  name: string;
  type: string;
}

export default function QueryWorkspaceModal({ onClose, initialView = "options" }: QueryWorkspaceModalProps) {
  const navigate = useNavigate();
  const [view, setView] = useState<"options" | "create">(initialView);
  const [createMode, setCreateMode] = useState<"ai" | "manual">("ai");
  
  // Table creation form states
  const [tableName, setTableName] = useState("");
  const [columns, setColumns] = useState<ColumnDef[]>([
    { name: "title", type: "VARCHAR(255)" },
    { name: "amount", type: "DOUBLE" }
  ]);
  const [aiPrompt, setAiPrompt] = useState("");
  const [schemaExplanation, setSchemaExplanation] = useState<string | null>(null);
  const [generatingSchema, setGeneratingSchema] = useState(false);
  const [createdSuccess, setCreatedSuccess] = useState<{ tableName: string; friendlyName: string } | null>(null);

  const [creating, setCreating] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleUseExisting = async () => {
    try {
      setResolving(true);
      setError(null);
      
      // 1. Try to fetch preview of currently active table
      const previewRes = await getPreview().catch(() => ({ success: false }));
      if (previewRes.success && previewRes.table_name) {
        const friendlyName = previewRes.table_name.split("_usr_")[0];
        sessionStorage.setItem("dataset", JSON.stringify({
          table_name: previewRes.table_name,
          filename: friendlyName,
          rows: previewRes.total_rows || 0,
          columns: previewRes.columns ? previewRes.columns.length : 0,
          missing_values: previewRes.total_missing || 0,
          detected_types: previewRes.detected_types || {}
        }));
        onClose();
        navigate("/dashboard");
        return;
      }
      
      // 2. If no active table is set, fetch the user's available datasets
      const datasetsRes = await getDatasets();
      if (datasetsRes.success && datasetsRes.datasets && datasetsRes.datasets.length > 0) {
        const firstTable = datasetsRes.datasets[0];
        const switchRes = await setActiveDataset(firstTable);
        if (switchRes.success) {
          const friendlyName = firstTable.split("_usr_")[0];
          sessionStorage.setItem("dataset", JSON.stringify({
            table_name: firstTable,
            filename: friendlyName,
            rows: 0,
            columns: 0,
            missing_values: 0,
            detected_types: {}
          }));
          onClose();
          navigate("/dashboard");
          return;
        }
      }
      
      // 3. If no datasets are uploaded, show error message instead of redirecting
      setError("No datasets present, upload dataset to work");
    } catch (e) {
      setError("No datasets present, upload dataset to work");
    } finally {
      setResolving(false);
    }
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

  const handleGenerateSchema = async () => {
    if (!aiPrompt.trim()) {
      setError("Please describe the table you want to create.");
      return;
    }

    try {
      setGeneratingSchema(true);
      setError(null);
      const res = await generateTableSchema(aiPrompt.trim());
      if (res.success && res.columns && res.columns.length > 0) {
        setTableName(res.table_name || "custom_table");
        setColumns(res.columns);
        setSchemaExplanation(res.explanation || null);
      } else {
        setError(res.error || "Failed to generate schema from description.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to generate schema. Please try refining your description.");
    } finally {
      setGeneratingSchema(false);
    }
  };

  const handleCreateTable = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
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
        const friendlyName = res.table_name.split("_usr_")[0];
        sessionStorage.setItem("dataset", JSON.stringify({
          table_name: res.table_name,
          filename: friendlyName,
          rows: 0,
          columns: columns.length + 1, // include id column
          missing_values: 0,
          detected_types: {}
        }));
        
        // Show success screen with action to populate
        setCreatedSuccess({
          tableName: res.table_name,
          friendlyName: friendlyName
        });
      } else {
        setError(res.error || "Failed to create table.");
      }
    } catch (err: any) {
      setError(err.message || "Failed to create table. Table name might be taken or contain reserved words.");
    } finally {
      setCreating(false);
    }
  };

  const handlePopulateWithChat = () => {
    if (!createdSuccess) return;
    onClose();
    // Navigate to dashboard and seed starter prompt in session
    sessionStorage.setItem("seed_chat_prompt", `Add to ${createdSuccess.friendlyName}: `);
    navigate("/dashboard");
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-3 sm:p-4">
      {/* Backdrop blur */}
      <div 
        onClick={onClose}
        className="absolute inset-0 bg-[#241C20]/60 backdrop-blur-md transition-opacity duration-300"
      />

      {/* Modal Container */}
      <div className={`relative bg-[#FFFDFC] border border-[#E8DED3] rounded-2xl sm:rounded-3xl p-4 sm:p-6 w-full shadow-2xl z-10 max-h-[85vh] sm:max-h-[88vh] flex flex-col transition-all duration-300 ${
        view === "create" ? "max-w-xl" : "max-w-sm"
      } animate-in fade-in zoom-in-95 duration-200`}>
        
        {/* Glow decoration */}
        <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[300px] h-[150px] bg-[#5A2F59]/5 rounded-full blur-[40px] pointer-events-none -z-10" />

        {/* Header - Fixed at top */}
        <div className="flex items-center justify-between mb-3 shrink-0">
          <div className="flex items-center gap-2">
            {view === "create" && (
              <button 
                onClick={() => { setView("options"); setError(null); setCreatedSuccess(null); }}
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
              {view === "create" ? "Custom Table Builder" : "Query Workspace"}
            </h3>
          </div>
          <button 
            onClick={onClose}
            className="w-7 h-7 bg-[#F7F2EC] hover:bg-[#E8DED3] rounded-full flex items-center justify-center text-[#6F6A67] hover:text-[#241C20] cursor-pointer transition-colors"
          >
            <X size={14} />
          </button>
        </div>

        {createdSuccess ? (
          /* Table Created Success View */
          <div className="py-3 text-center space-y-3 overflow-y-auto custom-scrollbar pr-1">
            <div className="w-11 h-11 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-600 flex items-center justify-center mx-auto">
              <CheckCircle2 size={22} />
            </div>
            <div>
              <h4 className="text-sm font-bold text-[#241C20]">
                Table Created Successfully!
              </h4>
              <p className="text-xs text-[#6F6A67] mt-1">
                Your custom table <strong className="text-[#172B4D] font-mono">{createdSuccess.friendlyName}</strong> is active and ready for data.
              </p>
            </div>

            <div className="p-3 bg-[#F7F2EC] rounded-xl border border-[#E8DED3] text-left text-xs space-y-1">
              <span className="text-[10px] uppercase font-bold text-[#BDA37A] tracking-wider block">Defined Columns</span>
              <div className="flex flex-wrap gap-1.5 pt-1">
                <span className="px-2 py-0.5 rounded bg-amber-500/10 text-amber-800 text-[10px] font-mono border border-amber-500/20">id (PK)</span>
                {columns.map((c, i) => (
                  <span key={i} className="px-2 py-0.5 rounded bg-white text-[#241C20] text-[10px] font-mono border border-[#E8DED3]">
                    {c.name} ({c.type})
                  </span>
                ))}
              </div>
            </div>

            <div className="flex flex-col sm:flex-row gap-2 pt-2">
              <button
                onClick={handlePopulateWithChat}
                className="flex-1 bg-[#168C88] hover:bg-[#137774] text-white py-2 px-3 rounded-xl font-semibold text-xs transition flex items-center justify-center gap-1.5 cursor-pointer shadow-sm"
              >
                <MessageSquarePlus size={14} />
                <span>Populate Records with AI Chat</span>
              </button>
              <button
                onClick={() => { onClose(); navigate("/dashboard"); }}
                className="bg-white border border-[#E8DED3] hover:bg-[#F7F2EC] text-[#241C20] py-2 px-3 rounded-xl font-medium text-xs transition cursor-pointer"
              >
                Go to Workspace
              </button>
            </div>
          </div>
        ) : view === "options" ? (
          <div className="overflow-y-auto custom-scrollbar pr-1">
            <p className="text-xs text-[#6F6A67] leading-relaxed mb-4">
              Would you like to continue querying your active dataset, upload a new spreadsheet file, or design a custom table with AI assistance?
            </p>

            {error && (
              <div className="mb-3 p-2.5 bg-red-500/5 border border-red-500/15 rounded-xl text-red-500 text-[10px] leading-tight font-medium">
                {error}
              </div>
            )}

            {/* Options */}
            <div className="space-y-2">
              <button
                onClick={handleUseExisting}
                disabled={resolving}
                className="w-full p-3 rounded-2xl bg-[#FFFDFC] border border-[#E8DED3] hover:border-[#5A2F59]/30 hover:bg-[#5A2F59]/3 flex items-center gap-3.5 transition-all duration-200 text-left cursor-pointer group shadow-sm disabled:opacity-75 disabled:cursor-not-allowed"
              >
                <div className="w-8 h-8 rounded-xl bg-[#5A2F59]/8 border border-[#5A2F59]/15 flex items-center justify-center text-[#5A2F59] shrink-0 group-hover:scale-105 transition-transform">
                  {resolving ? (
                    <Loader2 size={15} className="animate-spin text-[#5A2F59]" />
                  ) : (
                    <FileSpreadsheet size={15} />
                  )}
                </div>
                <div>
                  <h4 className="text-xs font-bold text-[#241C20] group-hover:text-[#5A2F59] transition-colors">
                    {resolving ? "Locating active dataset..." : "Use Active Dataset"}
                  </h4>
                  <p className="text-[9px] text-[#6F6A67] mt-0.5 leading-none">
                    Resume analyzing your loaded data
                  </p>
                </div>
              </button>

              {/* Upload new dataset option */}
              <button
                onClick={handleUploadNew}
                className="w-full p-3 rounded-2xl bg-[#FFFDFC] border border-[#E8DED3] hover:border-[#5A2F59]/30 hover:bg-[#5A2F59]/3 flex items-center gap-3.5 transition-all duration-200 text-left cursor-pointer group shadow-sm"
              >
                <div className="w-8 h-8 rounded-xl bg-[#5A2F59]/8 border border-[#5A2F59]/15 flex items-center justify-center text-[#5A2F59] shrink-0 group-hover:scale-105 transition-transform">
                  <Upload size={15} />
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
                className="w-full p-3 rounded-2xl bg-[#FFFDFC] border border-[#E8DED3] hover:border-[#5A2F59]/30 hover:bg-[#5A2F59]/3 flex items-center gap-3.5 transition-all duration-200 text-left cursor-pointer group shadow-sm"
              >
                <div className="w-8 h-8 rounded-xl bg-[#BDA37A]/15 border border-[#BDA37A]/30 flex items-center justify-center text-[#BDA37A] shrink-0 group-hover:scale-105 transition-transform">
                  <PlusCircle size={15} className="text-[#BDA37A]" />
                </div>
                <div>
                  <h4 className="text-xs font-bold text-[#241C20] group-hover:text-[#5A2F59] transition-colors flex items-center gap-1.5">
                    <span>Create Custom Table</span>
                    <span className="px-1.5 py-0.5 text-[8px] bg-[#168C88]/10 text-[#168C88] font-bold rounded-md uppercase">AI Powered</span>
                  </h4>
                  <p className="text-[9px] text-[#6F6A67] mt-0.5 leading-none">
                    Natural language or manual table design
                  </p>
                </div>
              </button>
            </div>
          </div>
        ) : (
          /* Create Table Form Subview with Tabs */
          <form onSubmit={handleCreateTable} className="flex flex-col flex-1 min-h-0 text-left">
            {/* Scrollable Form Body */}
            <div className="flex-1 overflow-y-auto pr-1 -mr-1 custom-scrollbar space-y-2.5">
              {/* Mode Switcher Tabs */}
              <div className="flex p-0.5 bg-[#F7F2EC] rounded-xl border border-[#E8DED3] text-xs font-medium">
                <button
                  type="button"
                  onClick={() => { setCreateMode("ai"); setError(null); }}
                  className={`flex-1 py-1.5 rounded-lg flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                    createMode === "ai"
                      ? "bg-white text-[#168C88] font-semibold shadow-xs"
                      : "text-[#6F6A67] hover:text-[#241C20]"
                  }`}
                >
                  <Sparkles size={12} className={createMode === "ai" ? "text-[#168C88]" : "text-[#6F6A67]"} />
                  <span>Option B: AI-Assisted</span>
                </button>
                <button
                  type="button"
                  onClick={() => { setCreateMode("manual"); setError(null); }}
                  className={`flex-1 py-1.5 rounded-lg flex items-center justify-center gap-1.5 transition-all cursor-pointer ${
                    createMode === "manual"
                      ? "bg-white text-[#5A2F59] font-semibold shadow-xs"
                      : "text-[#6F6A67] hover:text-[#241C20]"
                  }`}
                >
                  <Database size={12} className={createMode === "manual" ? "text-[#5A2F59]" : "text-[#6F6A67]"} />
                  <span>Option A: Manual</span>
                </button>
              </div>

              {error && (
                <div className="p-2.5 bg-red-500/5 border border-red-500/10 rounded-xl text-red-700 text-[11px] leading-tight">
                  {error}
                </div>
              )}

              {/* AI-Assisted Generation Input Area */}
              {createMode === "ai" && (
                <div className="bg-[#F7F2EC]/60 border border-[#E8DED3] rounded-xl p-2.5 sm:p-3 space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-[10px] font-bold text-[#168C88] uppercase tracking-wider flex items-center gap-1">
                      <Sparkles size={11} /> Describe Your Table
                    </label>
                    <span className="text-[9px] text-[#6F6A67]">Natural language schema generator</span>
                  </div>
                  <textarea
                    rows={2}
                    value={aiPrompt}
                    onChange={(e) => setAiPrompt(e.target.value)}
                    placeholder="e.g., Create an employee management table with employee name, department, joining date, salary and employment status."
                    className="w-full px-2.5 py-1.5 bg-white border border-[#E8DED3] focus:border-[#168C88] focus:ring-2 focus:ring-[#168C88]/15 rounded-lg text-[#241C20] placeholder-[#B0A79E] text-xs focus:outline-none transition-all resize-none"
                  />
                  <div className="flex justify-between items-center pt-0.5">
                    <span className="text-[9px] text-[#6F6A67] hidden sm:inline">
                      Infers types & excludes PK 'id'.
                    </span>
                    <button
                      type="button"
                      onClick={handleGenerateSchema}
                      disabled={generatingSchema || !aiPrompt.trim()}
                      className="ml-auto bg-[#168C88] hover:bg-[#137774] text-white px-2.5 py-1 rounded-lg text-xs font-semibold transition flex items-center gap-1 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed shadow-xs"
                    >
                      {generatingSchema ? (
                        <>
                          <Loader2 size={11} className="animate-spin" />
                          <span>Inferring...</span>
                        </>
                      ) : (
                        <>
                          <Sparkles size={11} />
                          <span>Generate Schema</span>
                        </>
                      )}
                    </button>
                  </div>
                </div>
              )}

              {schemaExplanation && createMode === "ai" && (
                <div className="px-2.5 py-1 bg-[#168C88]/5 border border-[#168C88]/15 rounded-lg text-[10px] text-[#168C88] font-medium">
                  💡 {schemaExplanation}
                </div>
              )}

              {/* Table Name Input */}
              <div>
                <label className="block text-[10px] font-bold text-[#BDA37A] uppercase tracking-wider mb-0.5">
                  Table Name
                </label>
                <input
                  type="text"
                  required
                  value={tableName}
                  onChange={(e) => setTableName(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
                  placeholder="e.g. employee_management"
                  className="w-full px-2.5 py-1.5 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#5A2F59] focus:ring-2 focus:ring-[#5A2F59]/15 rounded-lg text-[#241C20] placeholder-[#B0A79E] text-xs focus:outline-none transition-all"
                />
                <span className="text-[9px] text-[#6F6A67] mt-0.5 block">
                  Lowercase letters, numbers, and underscores only.
                </span>
              </div>

              {/* Columns List Header */}
              <div>
                <div className="flex justify-between items-center mb-1">
                  <label className="block text-[10px] font-bold text-[#BDA37A] uppercase tracking-wider">
                    {createMode === "ai" ? "Editable Schema Preview" : "Columns Configuration"}
                  </label>
                  <span className="text-[9px] text-emerald-700 bg-emerald-50 border border-emerald-200 px-1.5 py-0.5 rounded font-mono font-semibold">
                    ✓ 'id' INT AUTO_INCREMENT PK included
                  </span>
                </div>

                {/* Scrollable Column Configuration items */}
                <div className="max-h-36 sm:max-h-44 overflow-y-auto space-y-1 p-0.5 custom-scrollbar">
                  {columns.map((col, index) => (
                    <div key={index} className="flex gap-1.5 items-center">
                      <input
                        type="text"
                        required
                        value={col.name}
                        onChange={(e) => handleColumnChange(index, "name", e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, ""))}
                        placeholder="column_name"
                        className="flex-1 px-2.5 py-1.5 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#5A2F59] focus:ring-2 focus:ring-[#5A2F59]/15 rounded-lg text-[#241C20] placeholder-[#B0A79E] text-xs focus:outline-none transition-all"
                      />
                      <select
                        value={col.type}
                        onChange={(e) => handleColumnChange(index, "type", e.target.value)}
                        className="w-32 px-2 py-1.5 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#5A2F59] focus:ring-2 focus:ring-[#5A2F59]/15 rounded-lg text-[#241C20] text-xs focus:outline-none cursor-pointer transition-all shrink-0"
                      >
                        <option value="VARCHAR(255)">TEXT (Varchar)</option>
                        <option value="TEXT">LONG TEXT</option>
                        <option value="INT">INTEGER</option>
                        <option value="DOUBLE">NUMBER (Double)</option>
                        <option value="DECIMAL(10,2)">DECIMAL (10,2)</option>
                        <option value="DATE">DATE</option>
                        <option value="DATETIME">DATETIME</option>
                        <option value="BOOLEAN">BOOLEAN</option>
                      </select>
                      <button
                        type="button"
                        onClick={() => handleRemoveColumn(index)}
                        disabled={columns.length <= 1}
                        className="w-7 h-7 bg-red-500/5 hover:bg-red-500/10 text-red-600 rounded-lg flex items-center justify-center shrink-0 border border-red-500/10 hover:border-red-500/20 cursor-pointer transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
                        title="Remove column"
                      >
                        <Trash2 size={12} />
                      </button>
                    </div>
                  ))}
                </div>

                {/* Add Column Action */}
                <button
                  type="button"
                  onClick={handleAddColumn}
                  className="mt-1.5 flex items-center gap-1 text-xs text-[#5A2F59] hover:text-[#4A2549] font-bold cursor-pointer"
                >
                  <Plus size={13} />
                  <span>Add Column</span>
                </button>
              </div>
            </div>

            {/* Pinned Modal Footer */}
            <div className="pt-2.5 mt-2 border-t border-[#E8DED3]/60 shrink-0">
              <button
                type="submit"
                disabled={creating}
                className={`w-full py-2.5 rounded-xl font-semibold hover:scale-[1.005] active:scale-[0.995] transition-all duration-200 shadow-md cursor-pointer flex justify-center items-center gap-2 text-xs disabled:opacity-60 disabled:pointer-events-none text-white ${
                  createMode === "ai"
                    ? "bg-[#168C88] hover:bg-[#137774] shadow-[#168C88]/15"
                    : "bg-[#5A2F59] hover:bg-[#4A2549] shadow-[#5A2F59]/10"
                }`}
              >
                {creating ? (
                  <>
                    <Loader2 size={14} className="animate-spin" />
                    <span>Creating Table...</span>
                  </>
                ) : (
                  <>
                    <Database size={14} />
                    <span>{createMode === "ai" ? "Confirm & Create Table" : "Build Custom Table"}</span>
                  </>
                )}
              </button>
            </div>
          </form>
        )}

      </div>
    </div>
  );
}
