import { FileSpreadsheet, RefreshCw } from "lucide-react";


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

      </div>
    </div>
  );
}