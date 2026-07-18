import {
  LayoutDashboard,
  Database,
  Brain,
  MessageSquare,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  FileText,
  ClipboardList,
  Wand2,
  FolderOpen,
  Check,
  Trash2,
  LogOut,
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import { getDatasets, setActiveDataset, deleteDataset } from "../services/api";

interface Props {
  activeSection?: string;
  onSectionClick?: (section: string) => void;
}

const menuItems = [
  { id: "overview", name: "Overview & Stats", icon: LayoutDashboard },
  { id: "preview", name: "Data Table", icon: Database },
  { id: "chat", name: "Ask AI", icon: MessageSquare },
  { id: "reports", name: "Reports", icon: FileText },
  { id: "audit", name: "Audit Logs", icon: ClipboardList },
  { id: "cleaner", name: "AI Data Cleaner", icon: Wand2 },
];

export default function DashboardSidebar({
  activeSection = "overview",
  onSectionClick,
}: Props) {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);
  const [datasets, setDatasets] = useState<string[]>([]);
  const [currentTable, setCurrentTable] = useState<string | null>(null);

  const handleLogout = () => {
    localStorage.removeItem("promptsql_token");
    localStorage.removeItem("promptsql_user_id");
    localStorage.removeItem("promptsql_username");
    sessionStorage.clear();
    navigate("/login");
  };

  useEffect(() => {
    // Load current table from session storage
    try {
      const stored = JSON.parse(sessionStorage.getItem("dataset") || "{}");
      if (stored && stored.table_name) {
        setCurrentTable(stored.table_name);
      }
    } catch (e) {}

    // Fetch library
    getDatasets().then((res) => {
      if (res.success && res.datasets) {
        setDatasets(res.datasets);
      }
    });

    // Listen for dataset changes across tabs/components
    const handleDatasetModified = () => {
      getDatasets().then((res) => {
        if (res.success && res.datasets) {
          setDatasets(res.datasets);
        }
      });
    };
    window.addEventListener("dataset-modified", handleDatasetModified);
    return () => window.removeEventListener("dataset-modified", handleDatasetModified);
  }, []);

  const handleItemClick = (id: string) => {
    if (onSectionClick) {
      onSectionClick(id);
    } else {
      const element = document.getElementById(id);
      if (element) element.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  const handleDatasetSwitch = async (tableName: string) => {
    try {
      const res = await setActiveDataset(tableName);
      if (res.success) {
        setCurrentTable(tableName);
        // Update session storage
        const currentData = JSON.parse(sessionStorage.getItem("dataset") || "{}");
        const displayName = tableName.split("_usr_")[0];
        sessionStorage.setItem("dataset", JSON.stringify({ ...currentData, table_name: tableName, filename: displayName }));
        
        // Reload page to reflect new dataset or dispatch event
        window.location.reload();
      }
    } catch (e) {
      console.error("Failed to switch dataset:", e);
    }
  };

  const handleDatasetDelete = async (tableName: string) => {
    if (!confirm(`Are you sure you want to delete the dataset "${tableName.split("_usr_")[0]}"?`)) return;
    try {
      const res = await deleteDataset(tableName);
      if (res.success) {
        if (tableName === currentTable) {
          sessionStorage.removeItem("dataset");
          setCurrentTable(null);
          navigate("/upload");
        } else {
          const datasetsRes = await getDatasets();
          if (datasetsRes.success && datasetsRes.datasets) {
            setDatasets(datasetsRes.datasets);
          }
        }
      }
    } catch (e) {
      console.error("Failed to delete dataset:", e);
      alert("Failed to delete dataset: " + e);
    }
  };

  return (
    <div
      className={`h-screen bg-[#0D0D0F] border-r border-white/[0.06] flex flex-col justify-between sticky top-0 transition-all duration-300 ${
        collapsed ? "w-[68px]" : "w-60"
      }`}
    >
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {/* Logo */}
        <div className={`flex items-center border-b border-white/[0.06] ${collapsed ? "justify-center py-4 px-3" : "gap-3 px-5 py-4"}`}>
          <div
            onClick={() => navigate("/")}
            className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-lg flex items-center justify-center cursor-pointer hover:shadow-lg hover:shadow-indigo-500/25 transition-all shrink-0"
          >
            <Brain size={16} className="text-white" />
          </div>
          {!collapsed && (
            <div onClick={() => navigate("/")} className="cursor-pointer">
              <div className="text-sm font-bold text-white hover:text-indigo-300 transition-colors">PromptSQL</div>
              <div className="text-[9px] text-zinc-600 font-medium uppercase tracking-wider">Analytics Hub</div>
            </div>
          )}
        </div>

        {/* Dataset Library */}
        <div className={`px-3 pt-4 pb-2 ${collapsed ? "hidden" : "block"}`}>
          <div className="text-[9px] text-zinc-600 font-bold uppercase tracking-wider mb-2 px-2 flex items-center gap-1.5">
            <FolderOpen size={10} /> Dataset Library
          </div>
          <div className="space-y-0.5 max-h-32 overflow-y-auto pr-1 custom-scrollbar">
            {datasets.length === 0 && (
              <div className="text-[10px] text-zinc-600 px-2 italic">No datasets found</div>
            )}
            {datasets.map((db) => {
              const isCurrent = db === currentTable;
              // format display name
              const displayName = db.split("_usr_")[0];
              return (
                <div
                  key={db}
                  className={`w-full flex items-center justify-between px-2 py-1 rounded-md text-[11px] font-medium transition-colors group ${
                    isCurrent 
                      ? "bg-indigo-500/10 text-indigo-400 border border-indigo-500/20" 
                      : "text-zinc-400 hover:text-zinc-200 hover:bg-white/[0.04]"
                  }`}
                  title={db}
                >
                  <button
                    onClick={() => handleDatasetSwitch(db)}
                    className="flex-1 text-left truncate pr-2 cursor-pointer font-medium"
                  >
                    {displayName}
                  </button>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {isCurrent && <Check size={11} className="text-indigo-400" />}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDatasetDelete(db);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-red-400 text-zinc-500 rounded transition cursor-pointer"
                      title="Delete dataset"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
        {!collapsed && <div className="mx-4 my-2 border-t border-white/[0.06]"></div>}

        {/* Nav items */}
        <div className="p-3 space-y-0.5">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeSection === item.id;
            return (
              <button
                key={item.id}
                onClick={() => handleItemClick(item.id)}
                title={collapsed ? item.name : undefined}
                className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-lg transition-all duration-200 cursor-pointer group ${
                  isActive
                    ? "bg-indigo-500/15 text-indigo-300 border border-indigo-500/20"
                    : "text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.04]"
                } ${collapsed ? "justify-center" : ""}`}
              >
                <Icon
                  size={16}
                  className={`shrink-0 ${isActive ? "text-indigo-400" : "text-zinc-600 group-hover:text-zinc-300"}`}
                />
                {!collapsed && (
                  <span className="text-sm font-medium truncate">{item.name}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Bottom */}
      <div className="p-3 border-t border-white/[0.06] space-y-0.5 shrink-0">
        <button
          onClick={() => navigate("/upload")}
          title={collapsed ? "Upload new dataset" : undefined}
          className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-zinc-500 hover:text-zinc-200 hover:bg-white/[0.04] transition-all cursor-pointer ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <ArrowLeft size={16} className="text-zinc-600 shrink-0" />
          {!collapsed && <span className="text-sm font-medium">Upload New</span>}
        </button>

        <button
          onClick={handleLogout}
          title={collapsed ? "Logout" : undefined}
          className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-red-500/80 hover:text-red-400 hover:bg-red-500/10 transition-all cursor-pointer ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <LogOut size={16} className="text-red-500/70 shrink-0" />
          {!collapsed && <span className="text-sm font-medium">Logout</span>}
        </button>

        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center w-full p-2.5 rounded-lg text-zinc-600 hover:text-zinc-400 hover:bg-white/[0.04] transition-all cursor-pointer"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
    </div>
  );
}