import { FileSpreadsheet, Upload, RefreshCw } from "lucide-react";
import { useNavigate } from "react-router-dom";

interface Props {
  fileName?: string;
  onRefresh?: () => void;
  isRefreshing?: boolean;
}

export default function DashboardNavbar({ 
  fileName = "No file uploaded",
  onRefresh,
  isRefreshing = false
}: Props) {
  const navigate = useNavigate();

  return (
    <div className="bg-white border border-warmgray-100 rounded-2xl shadow-sm px-6 py-4 flex items-center justify-between sticky top-4 z-40 backdrop-blur-md bg-white/95">
      {/* File Info */}
      <div className="flex items-center gap-3">
        <div className="bg-terracotta-50 border border-terracotta-100 p-2.5 rounded-xl text-terracotta-650">
          <FileSpreadsheet size={20} className="text-terracotta-500" />
        </div>
        <div>
          <span className="text-[10px] font-bold text-warmgray-400 uppercase tracking-wider block">
            Active Dataset
          </span>
          <span className="text-base font-bold text-warmgray-900 truncate max-w-xs md:max-w-md block leading-tight mt-0.5">
            {fileName}
          </span>
        </div>
      </div>

      {/* Right Controls */}
      <div className="flex items-center gap-3">
        {onRefresh && (
          <button
            onClick={onRefresh}
            disabled={isRefreshing}
            className="p-2.5 text-warmgray-500 hover:text-terracotta-600 hover:bg-warmgray-50 border border-warmgray-100 rounded-xl transition cursor-pointer disabled:opacity-50"
            title="Refresh preview data"
          >
            <RefreshCw size={18} className={isRefreshing ? "animate-spin" : ""} />
          </button>
        )}

        <button
          onClick={() => navigate("/upload")}
          className="flex items-center gap-2 bg-gradient-to-r from-terracotta-500 to-terracotta-600 hover:from-terracotta-600 hover:to-terracotta-700 text-white font-bold px-4 py-2.5 rounded-xl transition shadow-md shadow-terracotta-500/10 hover:shadow-lg active:scale-95 text-sm cursor-pointer"
        >
          <Upload size={16} />
          <span className="hidden sm:inline">Upload New</span>
        </button>

        <div className="w-10 h-10 border border-warmgray-100 rounded-xl bg-gradient-to-br from-terracotta-50 to-sand-50 flex items-center justify-center font-bold text-terracotta-600 text-sm shadow-sm select-none">
          DB
        </div>
      </div>
    </div>
  );
}