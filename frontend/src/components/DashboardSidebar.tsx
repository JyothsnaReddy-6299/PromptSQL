import {
  LayoutDashboard,
  Database,
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
import { useState, useEffect, useRef } from "react";
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
  const [logoutExpanded, setLogoutExpanded] = useState(false);
  const logoutRef = useRef<HTMLDivElement>(null);

  const handleLogout = () => {
    localStorage.removeItem("promptsql_token");
    localStorage.removeItem("promptsql_user_id");
    localStorage.removeItem("promptsql_username");
    sessionStorage.clear();
    navigate("/");
  };

  const handleLogoutClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (!logoutExpanded) {
      setLogoutExpanded(true);
    } else {
      handleLogout();
    }
  };

  // Close expanded logout button when clicking outside
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (logoutRef.current && !logoutRef.current.contains(e.target as Node)) {
        setLogoutExpanded(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

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
        const displayName = tableName.split("_usr_")[0];
        setCurrentTable(tableName);
        sessionStorage.setItem("dataset", JSON.stringify({
          table_name: tableName,
          filename: displayName,
          rows: 0,
          columns: 0,
          missing_values: 0,
          detected_types: {}
        }));
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
      className={`h-screen bg-[#303841] flex flex-col justify-between sticky top-0 transition-all duration-300 sidebar-scrollbar z-30 ${
        collapsed ? "w-[68px]" : "w-60"
      }`}
    >
      <div className="flex-1 overflow-y-auto overflow-x-hidden">
        {/* Logo - Clean without unnecessary lines */}
        <div className={`flex items-center ${collapsed ? "justify-center py-4 px-3" : "gap-3 px-5 py-4"}`}>
          <div
            onClick={() => navigate("/")}
            className="w-8 h-8 bg-[#76ABAE] rounded-lg flex items-center justify-center cursor-pointer hover:shadow-lg hover:shadow-[#76ABAE]/30 transition-all shrink-0 border border-[#76ABAE]/40"
          >
            <Database size={16} className="text-[#303841]" />
          </div>
          {!collapsed && (
            <div onClick={() => navigate("/")} className="cursor-pointer">
              <div className="font-black italic tracking-tighter text-base select-none">
                <span className="text-white">Prompt</span>
                <span className="text-[#0DA4AA]">SQL</span>
              </div>
              <div className="text-[9px] text-[#76ABAE] font-semibold uppercase tracking-wider">Analytics Hub</div>
            </div>
          )}
        </div>

        {/* Dataset Library */}
        <div className={`px-3 pt-2 pb-2 ${collapsed ? "hidden" : "block"}`}>
          <div className="text-[9px] text-[#76ABAE] font-extrabold uppercase tracking-wider mb-2 px-2 flex items-center gap-1.5">
            <FolderOpen size={10} className="text-[#76ABAE]" /> Dataset Library
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
                      ? "bg-[#76ABAE]/20 text-white border border-[#76ABAE]/40"
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
                    {isCurrent && <Check size={11} className="text-[#76ABAE]" />}
                    <button
                      onClick={(e) => {
                        e.stopPropagation();
                        handleDatasetDelete(db);
                      }}
                      className="opacity-0 group-hover:opacity-100 p-0.5 hover:text-[#FF5722] text-white/50 rounded transition cursor-pointer"
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

        {/* Nav items */}
        <div className="p-3 space-y-1">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeSection === item.id;
            return (
              <button
                key={item.id}
                onClick={() => handleItemClick(item.id)}
                title={collapsed ? item.name : undefined}
                className={`flex items-center gap-3 w-full px-3 py-2 rounded-lg transition-all duration-200 cursor-pointer group ${
                  isActive
                    ? "bg-[#76ABAE] text-white font-semibold shadow-sm shadow-[#76ABAE]/30"
                    : "text-white/75 hover:text-white hover:bg-white/5"
                } ${collapsed ? "justify-center" : ""}`}
              >
                <Icon
                  size={15}
                  className={`shrink-0 ${isActive ? "text-white" : "text-white/60 group-hover:text-white"}`}
                />
                {!collapsed && (
                  <span className="text-xs font-medium truncate">{item.name}</span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Sidebar Footer - Only Logout Symbol, expands on click */}
      <div className="p-3 space-y-2 shrink-0">
        <div ref={logoutRef} className="flex items-center justify-center">
          <button
            onClick={handleLogoutClick}
            title={logoutExpanded ? "Click again to confirm Logout" : "Logout"}
            className={`group relative bg-[#FF4742] hover:bg-[#E93B36] text-white rounded-full flex items-center justify-center overflow-hidden shadow-md shadow-[#FF4742]/30 hover:shadow-lg hover:shadow-[#FF4742]/45 transition-all duration-300 ease-in-out cursor-pointer active:scale-95 ${
              logoutExpanded ? "w-28 h-9 px-3.5 gap-2" : "w-9 h-9 px-2 hover:w-28 hover:gap-2"
            }`}
          >
            <LogOut size={15} className="shrink-0 transition-transform duration-300 group-hover:scale-105" />
            <span
              className={`text-xs font-bold tracking-wide whitespace-nowrap overflow-hidden transition-all duration-300 ease-in-out ${
                logoutExpanded
                  ? "max-w-xs opacity-100 ml-1.5"
                  : "max-w-0 opacity-0 group-hover:max-w-xs group-hover:opacity-100 group-hover:ml-1.5"
              }`}
            >
              Logout
            </span>
          </button>
        </div>

        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center w-full p-1 rounded-lg text-[#76ABAE]/60 hover:text-[#76ABAE] hover:bg-white/5 transition-all cursor-pointer"
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
        >
          {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
        </button>
      </div>
    </div>
  );
}
