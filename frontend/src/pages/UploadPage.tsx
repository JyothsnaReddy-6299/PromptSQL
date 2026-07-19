import { ArrowLeft, Upload, FileSpreadsheet, Sparkles, Database, Loader2, X } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState, useRef } from "react";
import axios from "axios";

export default function UploadPage() {
  const navigate = useNavigate();
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [uploading, setUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState("");
  const [progress, setProgress] = useState(0);
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

      clearInterval(progressInterval);
      setProgress(100);

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
    <div className="relative min-h-screen overflow-hidden bg-[#F7F2EC] flex items-center justify-center p-4">
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

      <div className="relative z-10 w-full max-w-lg">
        {/* Back link */}
        <button
          onClick={() => navigate("/")}
          className="group inline-flex gap-1.5 items-center mb-8 text-[#6F6A67] hover:text-[#5A2F59] transition-colors font-medium text-sm cursor-pointer"
        >
          <ArrowLeft size={14} className="group-hover:-translate-x-0.5 transition-transform" />
          <span>Back to home</span>
        </button>

        <div className="bg-[#FFFDFC] border border-[#E8DED3] rounded-2xl p-7 shadow-xl shadow-[#5A2F59]/5">
          {/* Header */}
          <div className="mb-7">
            <div className="inline-flex items-center gap-1.5 bg-[#5A2F59]/8 border border-[#5A2F59]/20 px-3 py-1 rounded-full text-[#5A2F59] text-[11px] font-medium mb-4">
              <Sparkles size={10} className="animate-spin-slow" />
              <span>Dataset Agnostic Engine</span>
            </div>
            <h1 className="text-2xl font-bold text-[#241C20] tracking-tight">
              Upload your dataset
            </h1>
            <p className="text-[#6F6A67] mt-1.5 text-sm leading-relaxed">
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
                ? "border-[#5A2F59]/60 bg-[#5A2F59]/5"
                : selectedFile
                ? "border-[#3E8E5B]/40 bg-[#3E8E5B]/4 cursor-default"
                : "border-[#E8DED3] hover:border-[#5A2F59]/40 bg-[#F7F2EC] hover:bg-[#5A2F59]/3"
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
                <div className="w-12 h-12 bg-[#3E8E5B]/10 border border-[#3E8E5B]/25 rounded-xl flex items-center justify-center">
                  <FileSpreadsheet size={22} className="text-[#3E8E5B]" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-[#241C20]">{selectedFile.name}</p>
                  <p className="text-xs text-[#6F6A67] mt-0.5">{(selectedFile.size / 1024).toFixed(1)} KB</p>
                </div>
                <button
                  onClick={(e) => { e.stopPropagation(); setSelectedFile(null); setUploadStatus(""); }}
                  className="flex items-center gap-1 text-xs text-[#6F6A67] hover:text-[#241C20] bg-[#F7F2EC] hover:bg-[#E8DED3] px-3 py-1.5 rounded-lg transition-all border border-[#E8DED3] cursor-pointer"
                >
                  <X size={11} />
                  Remove file
                </button>
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

          {/* Error/status */}
          {uploadStatus && !uploadStatus.includes("successful") && (
            <div className="mt-4 p-3.5 rounded-xl border border-[#D95D39]/20 bg-[#D95D39]/6 flex gap-2.5 items-start">
              <div className="w-4 h-4 rounded-full bg-[#D95D39]/20 flex items-center justify-center shrink-0 mt-0.5">
                <span className="text-[#D95D39] text-[10px] font-bold">!</span>
              </div>
              <span className="text-xs text-[#D95D39] leading-relaxed">{uploadStatus}</span>
            </div>
          )}

          {/* Loading state */}
          {uploading ? (
            <div className="mt-5 bg-[#F7F2EC] rounded-xl p-6 border border-[#E8DED3] flex flex-col items-center justify-center text-center">
              <div className="relative mb-5">
                <div className="absolute inset-0 bg-[#5A2F59]/15 blur-xl rounded-full"></div>
                <div className="relative bg-[#FFFDFC] border border-[#E8DED3] w-14 h-14 rounded-2xl flex items-center justify-center shadow-md">
                  <Loader2 size={24} className="text-[#5A2F59] animate-spin" />
                </div>
              </div>
              <h3 className="text-[#241C20] font-medium text-sm mb-1.5 animate-pulse">
                Processing your dataset
              </h3>
              <p className="text-[#6F6A67] text-xs mb-5">
                Detecting schemas, datatypes, and generating analytics
              </p>

              <div className="w-full bg-[#E8DED3] rounded-full h-1.5 overflow-hidden">
                <div
                  style={{ width: `${progress}%` }}
                  className="bg-[#5A2F59] h-full rounded-full transition-all duration-300 relative"
                >
                  <div className="absolute inset-0 bg-[#BDA37A]/30 animate-pulse"></div>
                </div>
              </div>
            </div>
          ) : (
            selectedFile && (
              <button
                onClick={handleUpload}
                className="mt-5 w-full bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] py-3.5 rounded-xl font-semibold hover:scale-[1.01] active:scale-[0.99] transition-all duration-200 shadow-md shadow-[#5A2F59]/20 cursor-pointer flex justify-center items-center gap-2 text-sm"
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