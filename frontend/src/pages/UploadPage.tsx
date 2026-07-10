import { ArrowLeft, Upload, FileSpreadsheet, Sparkles, Check, Database, Loader2 } from "lucide-react";
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
  "Generating final stats & summary stats..."
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

  // Drag and drop handlers
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

      // Start step rotation
      const stepInterval = setInterval(() => {
        setLoadingStepIdx((prev) => {
          if (prev < LOADING_STEPS.length - 1) {
            return prev + 1;
          }
          return prev;
        });
      }, 1500);

      // Progress bar simulation
      const progressInterval = setInterval(() => {
        setProgress((prev) => {
          if (prev >= 90) {
            clearInterval(progressInterval);
            return 90;
          }
          return prev + Math.floor(Math.random() * 15) + 5;
        });
      }, 600);

      const formData = new FormData();
      formData.append("file", selectedFile);

      // API call using relative path
      const response = await axios.post("/upload", formData, {
        headers: {
          "Content-Type": "multipart/form-data",
        },
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
      console.error(error);
    }
  };

  return (
    <div className="relative min-h-screen overflow-hidden bg-warmgray-50 flex items-center justify-center p-4">
      {/* Decorative Blob */}
      <div className="absolute top-0 right-0 w-96 h-96 bg-terracotta-100 rounded-full blur-3xl opacity-30" />
      <div className="absolute bottom-0 left-0 w-96 h-96 bg-sand-100 rounded-full blur-3xl opacity-30" />

      <div className="relative z-10 w-full max-w-xl bg-white rounded-2xl border border-warmgray-100 p-6 md:p-8 shadow-xl transition-all duration-300">
        <button
          onClick={() => navigate("/")}
          className="group inline-flex gap-1.5 items-center mb-6 text-warmgray-500 hover:text-terracotta-500 transition-colors font-bold text-xs cursor-pointer"
        >
          <ArrowLeft size={14} className="group-hover:-translate-x-0.5 transition-transform" />
          <span>Back to Home</span>
        </button>

        <div className="mb-6">
          <div className="inline-flex items-center gap-1.5 bg-terracotta-50 border border-terracotta-100 px-2.5 py-1 rounded-full text-terracotta-700 text-[10px] font-bold mb-2">
            <Sparkles size={10} className="animate-spin-slow" />
            <span>Dataset Agnostic Engine</span>
          </div>
          <h1 className="text-2xl font-extrabold text-warmgray-900 tracking-tight">
            Upload Your Dataset
          </h1>
          <p className="text-warmgray-500 mt-1 text-xs font-medium">
            Load any structured CSV, XLS, or XLSX spreadsheet to start.
          </p>
        </div>

        {/* Drag and Drop Zone with moving animated border */}
        <div className="p-[2.5px] rounded-[20px] bg-gradient-to-r from-terracotta-100 via-terracotta-500 to-terracotta-100 animate-moving-border shadow-sm">
          <div
            onDragEnter={handleDrag}
            onDragOver={handleDrag}
            onDragLeave={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`relative rounded-[17px] p-8 text-center cursor-pointer bg-white transition-all duration-300 border border-dashed ${
              dragActive
                ? "border-terracotta-500 bg-terracotta-50/20 scale-99 shadow-inner"
                : selectedFile
                ? "border-emerald-300 bg-emerald-50/15"
                : "border-warmgray-200 hover:border-terracotta-300 bg-warmgray-50/10 hover:bg-warmgray-50/30"
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

          <div className="mx-auto w-14 h-14 bg-white rounded-xl border border-warmgray-100 flex items-center justify-center shadow-md shadow-warmgray-100">
            {selectedFile ? (
              <FileSpreadsheet size={24} className="text-emerald-500" />
            ) : (
              <Upload size={24} className="text-terracotta-500" />
            )}
          </div>

          {selectedFile ? (
            <div className="mt-4">
              <h3 className="text-base font-bold text-warmgray-900">
                File Selected
              </h3>
              <p className="mt-1 text-xs font-bold text-emerald-700 bg-emerald-50 inline-block px-2.5 py-0.5 rounded-full border border-emerald-100">
                📄 {selectedFile.name} ({(selectedFile.size / 1024).toFixed(1)} KB)
              </p>
              <p className="mt-1.5 text-[10px] text-warmgray-400">
                Click to browse or drag in another file
              </p>
            </div>
          ) : (
            <div className="mt-4">
              <h3 className="text-base font-bold text-warmgray-900">
                Drag & drop files here
              </h3>
              <p className="mt-1 text-warmgray-400 text-xs font-medium">
                or click to browse your computer
              </p>
              <p className="mt-4 text-[10px] text-warmgray-400">
                Supported formats: CSV, XLS, XLSX
              </p>
            </div>
          )}
        </div>
      </div>

        {/* Status Messaging */}
        {uploadStatus && (
          <div className={`mt-4 p-3 rounded-xl border text-xs flex gap-2 items-center ${
            uploadStatus.includes("successful")
              ? "bg-emerald-50 border-emerald-200 text-emerald-800"
              : "bg-red-50 border-red-200 text-red-800"
          }`}>
            {uploadStatus.includes("successful") ? (
              <Check size={14} className="text-emerald-600 shrink-0" />
            ) : (
              <span className="font-bold shrink-0 text-red-650">✕</span>
            )}
            <span>{uploadStatus}</span>
          </div>
        )}

        {/* Upload Action / Loading State */}
        {uploading ? (
          <div className="mt-6 bg-warmgray-950 text-white rounded-2xl p-4 font-mono text-[10px] shadow-xl">
            <div className="flex justify-between items-center mb-3">
              <span className="text-terracotta-300 flex items-center gap-1.5 font-bold">
                <Loader2 size={12} className="animate-spin text-terracotta-450" /> Ingesting Dataset
              </span>
              <span className="text-warmgray-400">{progress}%</span>
            </div>
            
            {/* Progress Bar */}
            <div className="w-full bg-warmgray-900 rounded-full h-1.5 mb-4 overflow-hidden">
              <div
                style={{ width: `${progress}%` }}
                className="bg-gradient-to-r from-terracotta-500 to-sand-300 h-full rounded-full transition-all duration-300"
              />
            </div>

            {/* Simulated steps logs */}
            <div className="space-y-1.5 text-warmgray-300">
              {LOADING_STEPS.map((step, idx) => {
                if (idx < loadingStepIdx) {
                  return (
                    <div key={idx} className="flex gap-1.5 items-center text-emerald-400 font-semibold">
                      <span>✓</span>
                      <span>{step}</span>
                    </div>
                  );
                } else if (idx === loadingStepIdx) {
                  return (
                    <div key={idx} className="flex gap-1.5 items-center text-terracotta-400 animate-pulse font-bold">
                      <span className="inline-block w-1 h-1 rounded-full bg-terracotta-400 animate-ping" />
                      <span>{step}</span>
                    </div>
                  );
                } else {
                  return (
                    <div key={idx} className="flex gap-1.5 items-center text-warmgray-700">
                      <span className="w-1 h-1 rounded-full bg-warmgray-900" />
                      <span>{step}</span>
                    </div>
                  );
                }
              })}
            </div>
          </div>
        ) : (
          <div className="mt-6 flex gap-4">
            {selectedFile && (
              <button
                onClick={handleUpload}
                className="w-full bg-gradient-to-r from-terracotta-500 to-terracotta-600 text-white py-3 rounded-xl font-bold hover:scale-102 active:scale-98 transition duration-200 shadow-md shadow-terracotta-500/10 cursor-pointer flex justify-center items-center gap-1.5 text-sm"
              >
                <Database size={16} />
                <span>Process & Ingest Data</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}