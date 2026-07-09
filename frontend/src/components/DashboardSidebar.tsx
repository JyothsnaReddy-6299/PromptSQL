import {
  LayoutDashboard,
  Database,
  Brain,
  MessageSquare,
  ArrowLeft,
  ChevronLeft,
  ChevronRight,
  FileText,
  ClipboardList
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

interface Props {
  activeSection?: string;
  onSectionClick?: (section: string) => void;
}

const menuItems = [
  { id: "overview", name: "Overview & Stats", icon: LayoutDashboard },
  { id: "preview", name: "Data Table Preview", icon: Database },
  { id: "chat", name: "Ask AI Assistant", icon: MessageSquare },
  { id: "reports", name: "Saved Reports", icon: FileText },
  { id: "audit", name: "Audit Logs", icon: ClipboardList }
];

export default function DashboardSidebar({
  activeSection = "overview",
  onSectionClick
}: Props) {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);

  const handleItemClick = (id: string) => {
    if (onSectionClick) {
      onSectionClick(id);
    } else {
      const element = document.getElementById(id);
      if (element) {
        element.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }
  };

  return (
    <div 
      className={`h-screen bg-warmgray-950 text-warmgray-300 border-r border-warmgray-900 flex flex-col justify-between sticky top-0 transition-all duration-300 ${
        collapsed ? "w-20" : "w-64"
      }`}
    >
      <div>
        {/* Header */}
        <div className="p-6 border-b border-warmgray-900 flex items-center justify-between">
          {!collapsed && (
            <div className="flex items-center gap-3">
              <div className="bg-gradient-to-br from-terracotta-500 to-terracotta-600 p-2 rounded-xl text-white">
                <Brain size={20} />
              </div>
              <div className="flex flex-col">
                <span className="text-lg font-black text-white tracking-tight">PromptSQL</span>
                <span className="text-[9px] text-warmgray-500 font-bold uppercase">Analytics Hub</span>
              </div>
            </div>
          )}
          {collapsed && (
            <div className="bg-gradient-to-br from-terracotta-500 to-terracotta-600 p-2 rounded-xl text-white mx-auto">
              <Brain size={20} />
            </div>
          )}
        </div>

        {/* Menu Items */}
        <div className="p-4 space-y-2">
          {menuItems.map((item) => {
            const Icon = item.icon;
            const isActive = activeSection === item.id;

            return (
              <button
                key={item.id}
                onClick={() => handleItemClick(item.id)}
                title={item.name}
                className={`flex items-center gap-3 w-full p-3.5 rounded-xl transition duration-200 cursor-pointer group ${
                  isActive
                    ? "bg-terracotta-500 text-white font-bold shadow-md shadow-terracotta-500/10"
                    : "hover:bg-warmgray-900 text-warmgray-400 hover:text-white"
                }`}
              >
                <Icon 
                  size={20} 
                  className={`${isActive ? "text-white" : "text-warmgray-500 group-hover:text-terracotta-400"}`} 
                />
                {!collapsed && (
                  <span className="text-sm truncate">
                    {item.name}
                  </span>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* Footer controls */}
      <div className="p-4 border-t border-warmgray-900 space-y-2">
        <button
          onClick={() => navigate("/upload")}
          className="flex items-center gap-3 w-full p-3.5 rounded-xl hover:bg-warmgray-900 text-warmgray-400 hover:text-white transition duration-200 cursor-pointer"
          title="Upload new dataset"
        >
          <ArrowLeft size={20} className="text-warmgray-500" />
          {!collapsed && <span className="text-sm font-semibold">Upload New</span>}
        </button>

        <button
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center w-full p-2.5 rounded-lg bg-warmgray-900/40 hover:bg-warmgray-900 text-warmgray-500 hover:text-warmgray-300 transition duration-200 cursor-pointer"
        >
          {collapsed ? <ChevronRight size={18} /> : <ChevronLeft size={18} />}
        </button>
      </div>
    </div>
  );
}