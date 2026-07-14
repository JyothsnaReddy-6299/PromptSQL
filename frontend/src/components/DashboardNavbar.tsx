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
    <div className="bg-[#111113]/90 backdrop-blur-xl border-b border-white/[0.06] px-6 py-3.5 flex items-center justify-between sticky top-0 z-40">
      {/* File Info */}
      <div className="flex items-center gap-3">
        <div className="w-8 h-8 bg-indigo-500/10 border border-indigo-500/20 rounded-lg flex items-center justify-center">
          <FileSpreadsheet size={15} className="text-indigo-400" />
        </div>
        <div>
          <span className="text-[10px] font-semibold text-zinc-600 uppercase tracking-wider block">
            Active Dataset
          </span>
          <span className="text-sm font-semibold text-white truncate max-w-xs md:max-w-md block leading-tight">
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
            className="p-2 text-zinc-500 hover:text-white hover:bg-white/[0.05] border border-white/[0.06] hover:border-white/[0.12] rounded-lg transition-all cursor-pointer disabled:opacity-40"
            title="Refresh preview data"
          >
            <RefreshCw size={15} className={isRefreshing ? "animate-spin" : ""} />
          </button>
        )}
        <button
          onClick={() => navigate("/upload")}
          className="flex items-center gap-2 bg-white/[0.05] hover:bg-white/[0.08] border border-white/[0.07] hover:border-white/[0.15] text-zinc-400 hover:text-white px-3.5 py-2 rounded-lg text-xs font-medium transition-all cursor-pointer"
        >
          <Upload size={13} />
          <span>New Dataset</span>
        </button>
      </div>
    </div>
  );
}