import {
  LayoutDashboard,
  Database,
  Brain,
  MessageSquare,
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
        const currentData = JSON.parse(sessionStorage.getItem("dataset") || "{}");
        const displayName = tableName.split("_usr_")[0];
        sessionStorage.setItem("dataset", JSON.stringify({ ...currentData, table_name: tableName, filename: displayName }));
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
      className={`h-screen bg-[#34182F] border-r border-[#5A2F59]/30 flex flex-col justify-between sticky top-0 transition-all duration-300 sidebar-scrollbar ${
        collapsed ? "w-[68px]" : "w-60"
      }`}
    >
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {/* Logo */}
        <div className={`flex items-center border-b border-[#5A2F59]/30 ${collapsed ? "justify-center py-4 px-3" : "gap-3 px-5 py-4"}`}>
          <div
            onClick={() => navigate("/")}
            className="w-8 h-8 bg-[#5A2F59] rounded-lg flex items-center justify-center cursor-pointer hover:shadow-lg hover:shadow-[#5A2F59]/40 transition-all shrink-0 border border-[#BDA37A]/20"
          >
            <Brain size={16} className="text-[#BDA37A]" />
          </div>
          {!collapsed && (
            <div onClick={() => navigate("/")} className="cursor-pointer">
              <div className="text-sm font-bold text-white hover:text-[#BDA37A] transition-colors">PromptSQL</div>
              <div className="text-[9px] text-[#BDA37A]/75 font-semibold uppercase tracking-wider">Analytics Hub</div>
            </div>
          )}
        </div>

        {/* Dataset Library */}
        <div className={`px-3 pt-4 pb-2 ${collapsed ? "hidden" : "block"}`}>
          <div className="text-[9px] text-[#BDA37A] font-extrabold uppercase tracking-wider mb-2 px-2 flex items-center gap-1.5">
            <FolderOpen size={10} className="text-[#BDA37A]" /> Dataset Library
          </div>
          <div className="space-y-0.5 max-h-32 overflow-y-auto pr-1 custom-scrollbar">
            {datasets.length === 0 && (
              <div className="text-[10px] text-white/50 px-2 italic">No datasets found</div>
            )}
            {datasets.map((db) => {
              const isCurrent = db === currentTable;
              const displayName = db.split("_usr_")[0];
              return (
                <div
                  key={db}
                  className={`w-full flex items-center justify-between px-2 py-1 rounded-md text-[11px] font-medium transition-colors group ${
                    isCurrent
                      ? "bg-[#BDA37A]/20 text-white border border-[#BDA37A]/30"
                      : "text-white/70 hover:text-white hover:bg-white/5"
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
                    {isCurrent && <Check size={11} className="text-white" />}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDatasetDelete(db);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-[#D95D39] text-white/50 rounded transition cursor-pointer"
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
        {!collapsed && <div className="mx-4 my-2 border-t border-[#5A2F59]/30"></div>}

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
                    ? "bg-[#5A2F59] text-white border border-[#BDA37A]/20"
                    : "text-white/70 hover:text-white hover:bg-white/5"
                } ${collapsed ? "justify-center" : ""}`}
              >
                <Icon
                  size={16}
                  className={`shrink-0 ${isActive ? "text-white" : "text-white/50 group-hover:text-white"}`}
                />
                {!collapsed && (
                  <span className="text-sm font-medium truncate">{item.name}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      <div className="p-2 border-t border-[#5A2F59]/30 space-y-0.5 shrink-0">

        <button
          onClick={handleLogout}
          title={collapsed ? "Logout" : undefined}
          className={`flex items-center gap-3 w-full px-3 py-1.5 rounded-lg text-white/70 hover:text-[#D95D39] hover:bg-[#D95D39]/10 transition-all cursor-pointer ${
            collapsed ? "justify-center" : ""
          }`}
        >
          <LogOut size={15} className="text-white/50 group-hover:text-[#D95D39] shrink-0" />
          {!collapsed && <span className="text-xs font-medium">Logout</span>}
        </button>

        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center w-full p-1.5 rounded-lg text-[#BDA37A]/40 hover:text-[#BDA37A] hover:bg-white/5 transition-all cursor-pointer"
        >
          {collapsed ? <ChevronRight size={15} /> : <ChevronLeft size={15} />}
        </button>
      </div>
    </div>
  );
}