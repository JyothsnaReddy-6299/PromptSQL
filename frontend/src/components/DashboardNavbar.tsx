import { FileSpreadsheet, RefreshCw, Upload } from "lucide-react";
import { useNavigate } from "react-router-dom";

interface Props {
  fileName?: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export default function DashboardNavbar({
  fileName = "No file uploaded",
  onRefresh,
  isRefreshing = false,
}: Props) {
  const navigate = useNavigate();

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
        <button
          onClick={() => navigate("/upload")}
          className="flex items-center gap-2 bg-[#5A2F59] hover:bg-[#4A2549] text-white px-3.5 py-2 rounded-lg text-xs font-semibold shadow-sm shadow-[#5A2F59]/10 transition-all cursor-pointer"
        >
          <Upload size={13} />
          <span>New Dataset</span>
        </button>
      </div>
    </div>
  );
}