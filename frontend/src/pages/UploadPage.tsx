import { ArrowLeft, Upload, FileSpreadsheet, Sparkles, Check, Database, Loader2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState, useRef } from "react";
import axios from "axios";

const LOADING_STEPS = [
  "Reading dataset files...",
  "Analyzing dataset schemas & structural formats...",
  "Detecting database types & columns...",
  "Running data cleaners & cleaning missing values...",
  "Preparing SQL schema mapping...",
  "Loading dataset into secure MySQL engine...",
  "Generating final stats & summary stats...",
];

export default function UploadPage() {
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [progress, setProgress] = useState(0);
  const [loadingStepIdx, setLoadingStepIdx] = useState(0);
  const [dragActive, setDragActive] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

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
      const file = e.dataTransfer.files[0];
      const ext = file.name.split(".").pop()?.toLowerCase();
      if (ext === "csv" || ext === "xlsx" || ext === "xls") {
        setSelectedFile(file);
        setUploadStatus("");
      } else {
        setUploadStatus("Unsupported file type. Please upload CSV or Excel.");
      }
    }
  };

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setSelectedFile(e.target.files[0]);
      setUploadStatus("");
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
      setLoadingStepIdx(0);

      const stepInterval = setInterval(() => {
        setLoadingStepIdx((prev) => {
          if (prev < LOADING_STEPS.length - 1) return prev + 1;
          return prev;
        });
      }, 1500);

      const progressInterval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 90) { clearInterval(progressInterval); return 90; }
          return prev + Math.floor(Math.random() * 15) + 5;
        });
      }, 600);

      const formData = new FormData();
      formData.append("file", selectedFile);

      const response = await axios.post("/upload", formData, {
        headers: { "Content-Type": "multipart/form-data" },
      });

      clearInterval(stepInterval);
      clearInterval(progressInterval);
      setProgress(100);
      setLoadingStepIdx(LOADING_STEPS.length - 1);

      setTimeout(() => {
        setUploading(false);
        setUploadStatus("Upload successful");
        sessionStorage.setItem("dataset", JSON.stringify(response.data));
        navigate("/dashboard", { state: response.data });
      }, 1000);

    } catch (error: any) {
      setUploading(false);
      setProgress(0);
      const errMsg = error.response?.data?.detail || "Upload failed. Please verify MySQL configuration and try again.";
      setUploadStatus(errMsg);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-[#09090B] flex items-center justify-center p-4">
      {/* Background glow */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[700px] h-[500px] bg-indigo-600/[0.08] rounded-full blur-[100px]" />
      </div>

      {/* Grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.02] pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(rgba(255,255,255,0.1) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.1) 1px, transparent 1px)`,
          backgroundSize: "80px 80px",
        }}
      />

      <div className="relative z-10 w-full max-w-lg">
        {/* Back link */}
        <button
          onClick={() => navigate("/")}
          className="group inline-flex gap-1.5 items-center mb-8 text-zinc-500 hover:text-white transition-colors font-medium text-sm cursor-pointer"
        >
          <ArrowLeft size={14} className="group-hover:-translate-x-0.5 transition-transform" />
          <span>Back to home</span>
        </button>

        <div className="bg-[#111113] border border-white/[0.07] rounded-2xl p-7 shadow-2xl shadow-black/40">
          {/* Header */}
          <div className="mb-7">
            <div className="inline-flex items-center gap-1.5 bg-indigo-500/10 border border-indigo-500/20 px-3 py-1 rounded-full text-indigo-400 text-[11px] font-medium mb-4">
              <Sparkles size={10} className="animate-spin-slow" />
              <span>Dataset Agnostic Engine</span>
            </div>
            <h1 className="text-2xl font-bold text-white tracking-tight">
              Upload your dataset
            </h1>
            <p className="text-zinc-500 mt-1.5 text-sm leading-relaxed">
              Load any structured CSV, XLS, or XLSX file to start querying with AI.
            </p>
          </div>

          {/* Drop zone */}
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => !selectedFile && fileInputRef.current?.click()}
            className={`relative rounded-xl border-2 border-dashed p-8 text-center cursor-pointer transition-all duration-300 ${
              dragActive
                ? "border-indigo-500/60 bg-indigo-500/[0.04]"
                : selectedFile
                ? "border-emerald-500/40 bg-emerald-500/[0.04] cursor-default"
                : "border-white/[0.1] hover:border-white/[0.2] bg-white/[0.02] hover:bg-white/[0.04]"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.xlsx,.xls"
              onChange={handleFileSelect}
              onClick={(e) => e.stopPropagation()}
              className="hidden"
            />

            {selectedFile ? (
              <div className="flex flex-col items-center gap-3">
                <div className="w-12 h-12 bg-emerald-500/10 border border-emerald-500/20 rounded-xl flex items-center justify-center">
                  <FileSpreadsheet size={22} className="text-emerald-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">{selectedFile.name}</p>
                  <p className="text-xs text-zinc-500 mt-0.5">{(selectedFile.size / 1024).toFixed(1)} KB</p>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setSelectedFile(null); setUploadStatus(""); }}
                  className="flex items-center gap-1 text-xs text-zinc-500 hover:text-white bg-white/[0.05] hover:bg-white/[0.08] px-3 py-1.5 rounded-lg transition-all border border-white/[0.06] cursor-pointer"
                >
                  <X size={11} />
                  Remove file
                </button>
              </div>
            ) : (
              <div className="flex flex-col items-center gap-3">
                <div className="w-12 h-12 bg-white/[0.04] border border-white/[0.08] rounded-xl flex items-center justify-center">
                  <Upload size={20} className="text-zinc-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white">
                    {dragActive ? "Drop your file here" : "Drag & drop your dataset"}
                  </p>
                  <p className="text-xs text-zinc-500 mt-1">or click to browse — CSV, XLS, XLSX</p>
                </div>
              </div>
            )}
          </div>

          {/* Error/status */}
          {uploadStatus && !uploadStatus.includes("successful") && (
            <div className="mt-4 p-3.5 rounded-xl border border-red-500/20 bg-red-500/[0.06] flex gap-2.5 items-start">
              <div className="w-4 h-4 rounded-full bg-red-500/20 flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-red-400 text-[10px] font-bold">!</span>
              </div>
              <span className="text-xs text-red-400 leading-relaxed">{uploadStatus}</span>
            </div>
          )}

          {/* Loading state */}
          {uploading ? (
            <div className="mt-5 bg-[#0D0D0F] rounded-xl p-5 border border-white/[0.06] font-mono text-[11px]">
              <div className="flex justify-between items-center mb-3">
                <span className="text-indigo-400 flex items-center gap-2 font-medium">
                  <Loader2 size={12} className="animate-spin" />
                  Ingesting dataset...
                </span>
                <span className="text-zinc-600">{progress}%</span>
              </div>

              <div className="w-full bg-white/[0.05] rounded-full h-1 mb-4 overflow-hidden">
                <div
                  style={{ width: `${progress}%` }}
                  className="bg-gradient-to-r from-indigo-500 to-violet-500 h-full rounded-full transition-all duration-300"
                />
              </div>

              <div className="space-y-2">
                {LOADING_STEPS.map((step, idx) => {
                  if (idx < loadingStepIdx) {
                    return (
                      <div key={idx} className="flex gap-2 items-center text-emerald-400">
                        <Check size={11} />
                        <span className="text-zinc-500">{step}</span>
                      </div>
                    );
                  } else if (idx === loadingStepIdx) {
                    return (
                      <div key={idx} className="flex gap-2 items-center text-indigo-400 font-semibold">
                        <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-ping shrink-0" />
                        <span>{step}</span>
                      </div>
                    );
                  } else {
                    return (
                      <div key={idx} className="flex gap-2 items-center text-zinc-700">
                        <span className="w-1 h-1 rounded-full bg-zinc-800 shrink-0 ml-0.5" />
                        <span>{step}</span>
                      </div>
                    );
                  }
                })}
              </div>
            </div>
          ) : (
            selectedFile && (
              <button
                onClick={handleUpload}
                className="mt-5 w-full bg-white hover:bg-zinc-50 text-zinc-900 py-3.5 rounded-xl font-semibold hover:scale-[1.01] active:scale-[0.99] transition-all duration-200 shadow-lg shadow-black/20 cursor-pointer flex justify-center items-center gap-2 text-sm"
              >
                <Database size={15} />
                <span>Process & Ingest Data</span>
              </button>
            )
          )}

          {/* Formats hint */}
          {!selectedFile && !uploading && (
            <div className="mt-5 flex items-center justify-center gap-4">
              {[".CSV", ".XLS", ".XLSX"].map((fmt) => (
                <span key={fmt} className="text-[10px] text-zinc-600 bg-white/[0.03] border border-white/[0.06] px-2.5 py-1 rounded-md font-mono">
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