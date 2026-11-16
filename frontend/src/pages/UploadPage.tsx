import {
  ArrowLeft,
  Upload,
  FileSpreadsheet,
  Sparkles,
  Database,
  Loader2,
  X,
  Layers,
  AlertTriangle,
  Table
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState, useRef } from "react";
import axios from "axios";

interface ExcelPreviewData {
  sheets: string[];
  selected_sheet: string;
  detected_header_row: number;
  selected_header_row: number;
  confidence: number;
  is_ambiguous: boolean;
  columns: string[];
  preview_rows: Record<string, any>[];
  total_rows: number;
  warnings: string[];
  filename?: string;
}

export default function UploadPage() {
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Issue 18: Excel Preview & Header Detection State
  const [isExcel, setIsExcel] = useState(false);
  const [excelPreview, setExcelPreview] = useState<ExcelPreviewData | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [selectedSheet, setSelectedSheet] = useState<string>("");
  const [selectedHeaderRow, setSelectedHeaderRow] = useState<number>(1);

  const fetchExcelPreview = async (file: File, sheet?: string, headerRow?: number) => {
    try {
      setLoadingPreview(true);
      setUploadStatus("");
      const formData = new FormData();
      formData.append("file", file);
      if (sheet) formData.append("sheet_name", sheet);
      if (headerRow !== undefined && headerRow !== null) {
        formData.append("header_row", headerRow.toString());
      }

      const res = await axios.post("/upload/preview-excel", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      if (res.data && res.data.success) {
        setExcelPreview(res.data);
        setSelectedSheet(res.data.selected_sheet);
        setSelectedHeaderRow(res.data.selected_header_row);
      }
    } catch (err: any) {
      const errMsg = err.response?.data?.detail || "Failed to inspect Excel workbook.";
      setUploadStatus(errMsg);
    } finally {
      setLoadingPreview(false);
    }
  };

  const handleFileProcess = (file: File) => {
    const ext = file.name.split(".").pop()?.toLowerCase();
    if (ext === "csv" || ext === "xlsx" || ext === "xls") {
      setSelectedFile(file);
      setUploadStatus("");
      if (ext === "xlsx" || ext === "xls") {
        setIsExcel(true);
        fetchExcelPreview(file);
      } else {
        setIsExcel(false);
        setExcelPreview(null);
      }
    } else {
      setUploadStatus("Unsupported file type. Please upload a CSV, XLS, or XLSX file.");
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileProcess(e.dataTransfer.files[0]);
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      handleFileProcess(e.target.files[0]);
    }
  };

  const handleSheetChange = (newSheet: string) => {
    if (!selectedFile || newSheet === selectedSheet) return;
    setSelectedSheet(newSheet);
    fetchExcelPreview(selectedFile, newSheet, undefined);
  };

  const handleHeaderRowChange = (newRow: number) => {
    if (!selectedFile || newRow < 1) return;
    setSelectedHeaderRow(newRow);
    fetchExcelPreview(selectedFile, selectedSheet, newRow);
  };

  const resetSelection = () => {
    setSelectedFile(null);
    setExcelPreview(null);
    setIsExcel(false);
    setUploadStatus("");
    setProgress(0);
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleUpload = async () => {
    if (!selectedFile) {
      setUploadStatus("Please select a file first.");
      return;
    }

    try {
      setUploading(true);
      setProgress(5);

      const progressInterval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 90) { clearInterval(progressInterval); return 90; }
          return prev + Math.floor(Math.random() * 15) + 5;
        });
      }, 500);

      const formData = new FormData();
      formData.append("file", selectedFile);
      if (isExcel) {
        if (selectedSheet) formData.append("sheet_name", selectedSheet);
        if (selectedHeaderRow) formData.append("header_row", selectedHeaderRow.toString());
      }

      const response = await axios.post("/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      clearInterval(progressInterval);
      setProgress(100);

      setTimeout(() => {
        setUploading(false);
        setUploadStatus("Upload successful");
        sessionStorage.setItem("dataset", JSON.stringify(response.data));
        navigate("/dashboard", { state: response.data });
      }, 800);

    } catch (error: any) {
      setUploading(false);
      setProgress(0);
      const errMsg = error.response?.data?.detail || "Upload failed. Please verify MySQL configuration and try again.";
      setUploadStatus(errMsg);
    }
  };

  return (
    <div className="relative min-h-screen bg-[#F7F2EC] flex items-center justify-center p-4 md:p-8">
      {/* Warm background glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[500px] bg-[#5A2F59]/6 rounded-full blur-[100px]" />
        <div className="absolute bottom-1/4 right-1/4 w-[400px] h-[400px] bg-[#BDA37A]/8 rounded-full blur-[80px]" />
      </div>

      {/* Subtle warm grid */}
      <div
        className="absolute inset-0 opacity-[0.03] pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(rgba(90,47,89,0.2) 1px, transparent 1px), linear-gradient(90deg, rgba(90,47,89,0.2) 1px, transparent 1px)`,
          backgroundSize: "80px 80px",
        }}
      />

      <div className={`relative z-10 w-full transition-all duration-300 ${isExcel && excelPreview ? "max-w-4xl" : "max-w-lg"}`}>
        {/* Back link */}
        <button
          onClick={() => navigate("/")}
          className="group inline-flex gap-1.5 items-center mb-4 text-[#6F6A67] hover:text-[#5A2F59] transition-colors font-medium text-sm cursor-pointer"
        >
          <ArrowLeft size={14} className="group-hover:-translate-x-0.5 transition-transform" />
          <span>Back to home</span>
        </button>

        <div className="bg-[#FFFDFC] border border-[#E8DED3] rounded-2xl p-6 md:p-7 shadow-xl shadow-[#5A2F59]/5">
          {/* Header */}
          <div className="mb-5">
            <div className="inline-flex items-center gap-1.5 bg-[#5A2F59]/8 border border-[#5A2F59]/20 px-3 py-1 rounded-full text-[#5A2F59] text-[11px] font-medium mb-2.5">
              <Sparkles size={10} className="animate-spin-slow" />
              <span>Intelligent Dataset Engine</span>
            </div>
            <h1 className="text-xl font-bold text-[#241C20] tracking-tight">
              {isExcel && excelPreview ? "Excel Import Preview & Header Selection" : "Upload your dataset"}
            </h1>
            <p className="text-[#6F6A67] mt-1 text-xs leading-relaxed">
              {isExcel && excelPreview
                ? "Verify the detected heading row, choose worksheets, and inspect sample records before ingesting."
                : "Load any structured CSV, XLS, or XLSX file to start querying with AI."}
            </p>
          </div>

          {/* Regular Upload Drop Zone (hidden if excel preview is active) */}
          {(!isExcel || !excelPreview) && (
            <div
              onDragEnter={handleDrag}
              onDragOver={handleDrag}
              onDragLeave={handleDrag}
              onDrop={handleDrop}
              onClick={() => !selectedFile && !uploading && fileInputRef.current?.click()}
              className={`relative rounded-xl border-2 border-dashed p-8 text-center transition-all duration-300 ${
                dragActive
                  ? "border-[#5A2F59]/60 bg-[#5A2F59]/5"
                  : selectedFile
                  ? "border-[#3E8E5B]/40 bg-[#3E8E5B]/4 cursor-default"
                  : "border-[#E8DED3] hover:border-[#5A2F59]/40 bg-[#F7F2EC] hover:bg-[#5A2F59]/3"
              } ${uploading ? "cursor-default" : "cursor-pointer"}`}
            >
              <input
                ref={fileInputRef}
                type="file"
                accept=".csv,.xlsx,.xls"
                onChange={handleFileSelect}
                onClick={(e) => e.stopPropagation()}
                className="hidden"
              />

              {uploading ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="relative mb-2">
                    <div className="absolute inset-0 bg-[#5A2F59]/15 blur-xl rounded-full"></div>
                    <div className="relative bg-[#FFFDFC] border border-[#E8DED3] w-12 h-12 rounded-xl flex items-center justify-center shadow-sm">
                      <Loader2 size={20} className="text-[#5A2F59] animate-spin" />
                    </div>
                  </div>
                  <div>
                    <h3 className="text-[#241C20] font-semibold text-xs animate-pulse">
                      Processing {selectedFile?.name}
                    </h3>
                    <p className="text-[#6F6A67] text-[10px] mt-0.5">
                      Ingesting data, schemas, datatypes, and missing values
                    </p>
                  </div>
                  <div className="w-full bg-[#E8DED3] rounded-full h-1.5 overflow-hidden mt-2 relative">
                    <div
                      style={{ width: `${progress}%` }}
                      className="bg-[#5A2F59] h-full rounded-full transition-all duration-300 relative"
                    >
                      <div className="absolute inset-0 bg-[#BDA37A]/30 animate-pulse"></div>
                    </div>
                  </div>
                  <span className="text-[10px] font-bold text-[#5A2F59]">{progress}% Complete</span>
                </div>
              ) : selectedFile ? (
                <div className="flex flex-col items-center gap-3">
                  <div className="w-12 h-12 bg-[#3E8E5B]/10 border border-[#3E8E5B]/25 rounded-xl flex items-center justify-center">
                    <FileSpreadsheet size={22} className="text-[#3E8E5B]" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[#241C20]">{selectedFile.name}</p>
                    <p className="text-xs text-[#6F6A67] mt-0.5">{(selectedFile.size / 1024).toFixed(1)} KB</p>
                  </div>
                  {loadingPreview ? (
                    <div className="flex items-center gap-1.5 text-xs text-[#5A2F59] font-medium">
                      <Loader2 size={13} className="animate-spin" />
                      <span>Detecting Excel headers...</span>
                    </div>
                  ) : (
                    <button
                      onClick={(e) => { e.stopPropagation(); resetSelection(); }}
                      className="flex items-center gap-1 text-xs text-[#6F6A67] hover:text-[#241C20] bg-[#F7F2EC] hover:bg-[#E8DED3] px-3 py-1.5 rounded-lg transition-all border border-[#E8DED3] cursor-pointer"
                    >
                      <X size={11} />
                      Remove file
                    </button>
                  )}
                </div>
              ) : (
                <div className="flex flex-col items-center gap-3">
                  <div className="w-12 h-12 bg-[#5A2F59]/10 border border-[#5A2F59]/20 rounded-xl flex items-center justify-center">
                    <Upload size={20} className="text-[#5A2F59]" />
                  </div>
                  <div>
                    <p className="text-sm font-semibold text-[#241C20]">
                      {dragActive ? "Drop your file here" : "Drag & drop your dataset"}
                    </p>
                    <p className="text-xs text-[#6F6A67] mt-1">or click to browse — CSV, XLS, XLSX</p>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Issue 18: Rich Excel Preview & Header Controls Card */}
          {isExcel && excelPreview && (
            <div className="space-y-4">
              {/* File Info Bar */}
              <div className="flex flex-wrap items-center justify-between gap-3 p-3.5 bg-[#F7F2EC] border border-[#E8DED3] rounded-xl">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-lg bg-[#3E8E5B]/15 text-[#3E8E5B] flex items-center justify-center shrink-0">
                    <FileSpreadsheet size={16} />
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-[#241C20]">{selectedFile?.name}</p>
                    <p className="text-[11px] text-[#6F6A67]">
                      {excelPreview.total_rows.toLocaleString()} estimated records &bull; {excelPreview.columns.length} columns
                    </p>
                  </div>
                </div>

                <button
                  onClick={resetSelection}
                  disabled={uploading}
                  className="text-xs text-[#6F6A67] hover:text-[#241C20] px-2.5 py-1 rounded-md bg-[#FFFDFC] border border-[#E8DED3] transition-colors"
                >
                  Change File
                </button>
              </div>

              {/* Controls Grid: Worksheet & Header Row */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3.5">
                {/* Worksheet Selector */}
                <div className="p-3.5 bg-[#FFFDFC] border border-[#E8DED3] rounded-xl space-y-1.5">
                  <label className="text-[11px] font-semibold text-[#6F6A67] uppercase tracking-wider flex items-center gap-1.5">
                    <Layers size={13} className="text-[#5A2F59]" />
                    <span>Worksheet</span>
                  </label>
                  {excelPreview.sheets.length > 1 ? (
                    <select
                      value={selectedSheet}
                      onChange={(e) => handleSheetChange(e.target.value)}
                      disabled={loadingPreview || uploading}
                      className="w-full text-xs font-medium text-[#241C20] bg-[#F7F2EC] border border-[#E8DED3] rounded-lg px-3 py-2 outline-none focus:border-[#5A2F59] transition-colors cursor-pointer"
                    >
                      {excelPreview.sheets.map((s) => (
                        <option key={s} value={s}>{s}</option>
                      ))}
                    </select>
                  ) : (
                    <div className="text-xs font-medium text-[#241C20] bg-[#F7F2EC] border border-[#E8DED3] rounded-lg px-3 py-2">
                      {selectedSheet || "Default Sheet"}
                    </div>
                  )}
                </div>

                {/* Header Row Selector */}
                <div className="p-3.5 bg-[#FFFDFC] border border-[#E8DED3] rounded-xl space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-[11px] font-semibold text-[#6F6A67] uppercase tracking-wider flex items-center gap-1.5">
                      <Table size={13} className="text-[#5A2F59]" />
                      <span>Header Row Number</span>
                    </label>
                    <span className={`text-[10px] font-bold px-2 py-0.5 rounded-full ${
                      excelPreview.is_ambiguous
                        ? "bg-[#D95D39]/10 text-[#D95D39] border border-[#D95D39]/20"
                        : "bg-[#3E8E5B]/10 text-[#3E8E5B] border border-[#3E8E5B]/20"
                    }`}>
                      {excelPreview.is_ambiguous ? "Ambiguous (Confirm)" : `Detected (Row ${excelPreview.detected_header_row})`}
                    </span>
                  </div>

                  <div className="flex items-center gap-2">
                    <input
                      type="number"
                      min={1}
                      max={50}
                      value={selectedHeaderRow}
                      onChange={(e) => handleHeaderRowChange(parseInt(e.target.value) || 1)}
                      disabled={loadingPreview || uploading}
                      className="w-20 text-xs font-bold text-[#241C20] bg-[#F7F2EC] border border-[#E8DED3] rounded-lg px-3 py-2 outline-none focus:border-[#5A2F59] text-center"
                    />
                    <span className="text-[11px] text-[#6F6A67]">
                      {selectedHeaderRow === excelPreview.detected_header_row
                        ? "(Using auto-detected row)"
                        : "(Custom row selected)"}
                    </span>
                    {loadingPreview && <Loader2 size={13} className="text-[#5A2F59] animate-spin ml-auto" />}
                  </div>
                </div>
              </div>

              {/* Warnings List */}
              {excelPreview.warnings && excelPreview.warnings.length > 0 && (
                <div className="p-3 bg-[#BDA37A]/10 border border-[#BDA37A]/30 rounded-xl space-y-1">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-[#8B6B3E]">
                    <AlertTriangle size={13} />
                    <span>Import Notice</span>
                  </div>
                  <ul className="list-disc list-inside text-[11px] text-[#6F6A67] space-y-0.5">
                    {excelPreview.warnings.map((w, idx) => (
                      <li key={idx}>{w}</li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Detected Column Headings */}
              <div className="p-3.5 bg-[#FFFDFC] border border-[#E8DED3] rounded-xl space-y-2">
                <span className="text-[11px] font-semibold text-[#6F6A67] uppercase tracking-wider block">
                  Detected Columns ({excelPreview.columns.length})
                </span>
                <div className="flex flex-wrap gap-1.5 max-h-24 overflow-y-auto">
                  {excelPreview.columns.map((col, idx) => (
                    <span
                      key={idx}
                      className="text-[11px] font-medium text-[#241C20] bg-[#F7F2EC] border border-[#E8DED3] px-2.5 py-1 rounded-md"
                    >
                      {col}
                    </span>
                  ))}
                </div>
              </div>

              {/* Data Rows Preview Table */}
              <div className="p-3.5 bg-[#FFFDFC] border border-[#E8DED3] rounded-xl space-y-2">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-[#6F6A67] uppercase tracking-wider">
                    Data Records Preview (First {excelPreview.preview_rows.length} rows)
                  </span>
                  <span className="text-[11px] text-[#6F6A67]">Row {selectedHeaderRow} excluded</span>
                </div>

                <div className="border border-[#E8DED3] rounded-lg overflow-x-auto max-h-48 overflow-y-auto">
                  <table className="w-full text-left text-[11px] divide-y divide-[#E8DED3]">
                    <thead className="bg-[#F7F2EC] sticky top-0 text-[#241C20] font-semibold">
                      <tr>
                        {excelPreview.columns.map((c, idx) => (
                          <th key={idx} className="px-3 py-2 whitespace-nowrap">{c}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E8DED3] bg-[#FFFDFC]">
                      {excelPreview.preview_rows.map((row, rIdx) => (
                        <tr key={rIdx} className="hover:bg-[#F7F2EC]/50 transition-colors">
                          {excelPreview.columns.map((c, cIdx) => (
                            <td key={cIdx} className="px-3 py-1.5 whitespace-nowrap text-[#6F6A67]">
                              {row[c] !== null && row[c] !== undefined ? String(row[c]) : (
                                <span className="text-[#A29C99] italic">null</span>
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          )}

          {/* Error/status */}
          {uploadStatus && !uploadStatus.includes("successful") && (
            <div className="mt-4 p-3.5 rounded-xl border border-[#D95D39]/20 bg-[#D95D39]/6 flex gap-2.5 items-start">
              <div className="w-4 h-4 rounded-full bg-[#D95D39]/20 flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-[#D95D39] text-[10px] font-bold">!</span>
              </div>
              <span className="text-xs text-[#D95D39] leading-relaxed">{uploadStatus}</span>
            </div>
          )}

          {/* Action button */}
          {!uploading && selectedFile && (
            <button
              onClick={handleUpload}
              disabled={loadingPreview}
              className="mt-5 w-full bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] py-3.5 rounded-xl font-semibold hover:scale-[1.01] active:scale-[0.99] transition-all duration-200 shadow-md shadow-[#5A2F59]/20 cursor-pointer flex justify-center items-center gap-2 text-sm disabled:opacity-50"
            >
              <Database size={15} />
              <span>
                {isExcel ? "Confirm & Ingest Excel Dataset" : "Process & Ingest Data"}
              </span>
            </button>
          )}

          {/* Formats hint */}
          {!selectedFile && !uploading && (
            <div className="mt-5 flex items-center justify-center gap-4">
              {[".CSV", ".XLS", ".XLSX"].map((fmt) => (
                <span key={fmt} className="text-[10px] text-[#6F6A67] bg-[#F7F2EC] border border-[#E8DED3] px-2.5 py-1 rounded-md font-mono">
                  {fmt}
                </span>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
