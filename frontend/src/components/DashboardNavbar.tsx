import { useState, useRef, useEffect } from "react";
import { FileSpreadsheet, RefreshCw, Upload, Plus, ChevronDown, PlusCircle } from "lucide-react";
import { useNavigate } from "react-router-dom";

interface Props {
  fileName?: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
  onUploadClick?: () => void;
  onCreateTableClick?: () => void;
}

export default function DashboardNavbar({
  fileName = "No file uploaded",
  onRefresh,
  isRefreshing = false,
  onUploadClick,
  onCreateTableClick,
}: Props) {
  const navigate = useNavigate();
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close dropdown on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setDropdownOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  return (
    <div className="bg-[#FFFDFC] border-b border-[#E8DED3] px-6 py-3.5 flex items-center justify-between sticky top-0 z-40">
      {/* File Info */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-[#5A2F59]/8 border border-[#5A2F59]/20 rounded-lg flex items-center justify-center">
          <FileSpreadsheet size={15} className="text-[#5A2F59]" />
        </div>
        <div>
          <span className="text-[10px] font-bold text-[#BDA37A] uppercase tracking-wider block">
            Active Dataset
          </span>
          <span className="text-sm font-bold text-[#241C20] truncate max-w-xs md:max-w-md block leading-tight">
            {fileName}
          </span>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-2">
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="p-2 text-[#6F6A67] hover:text-[#241C20] hover:bg-[#5A2F59]/5 border border-[#E8DED3] rounded-lg transition-all cursor-pointer disabled:opacity-40"
            title="Refresh preview data"
          >
            <RefreshCw size={15} className={isRefreshing ? "animate-spin" : ""} />
          </button>
        )}

        {/* Dropdown container */}
        <div className="relative" ref={dropdownRef}>
          <button
            onClick={() => setDropdownOpen(!dropdownOpen)}
            className="flex items-center gap-2 bg-[#5A2F59] hover:bg-[#4A2549] text-white px-3.5 py-2 rounded-lg text-xs font-semibold shadow-sm shadow-[#5A2F59]/10 transition-all cursor-pointer"
          >
            <Plus size={13} />
            <span>New Dataset</span>
            <ChevronDown size={12} className={`opacity-80 transition-transform duration-200 ${dropdownOpen ? "rotate-180" : ""}`} />
          </button>

          {dropdownOpen && (
            <div className="absolute right-0 mt-2 w-48 bg-[#FFFDFC] border border-[#E8DED3] rounded-xl shadow-xl shadow-[#5A2F59]/8 py-1.5 z-50 text-left animate-in fade-in slide-in-from-top-2 duration-150">
              <button
                onClick={() => {
                  setDropdownOpen(false);
                  if (onUploadClick) {
                    onUploadClick();
                  } else {
                    navigate("/upload");
                  }
                }}
                className="w-full text-left px-4 py-2 text-xs text-[#6F6A67] hover:text-[#241C20] hover:bg-[#5A2F59]/5 transition-colors cursor-pointer flex items-center gap-2 font-medium"
              >
                <Upload size={13} className="text-[#5A2F59]" />
                <span>Upload Dataset File</span>
              </button>
              <button
                onClick={() => {
                  setDropdownOpen(false);
                  if (onCreateTableClick) {
                    onCreateTableClick();
                  }
                }}
                className="w-full text-left px-4 py-2 text-xs text-[#6F6A67] hover:text-[#241C20] hover:bg-[#5A2F59]/5 transition-colors cursor-pointer border-t border-[#E8DED3]/60 pt-2 mt-1.5 flex items-center gap-2 font-medium"
              >
                <PlusCircle size={13} className="text-[#BDA37A]" />
                <span>Create Custom Table</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}