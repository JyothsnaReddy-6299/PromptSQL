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
} from "lucide-react";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

interface Props {
  activeSection?: string;
  onSectionClick?: (section: string) => void;
}

const menuItems = [
  { id: "overview", name: "Overview & Stats", icon: LayoutDashboard },
  { id: "preview", name: "Data Table", icon: Database },
  { id: "cleaner", name: "AI Data Cleaner", icon: Wand2 },
  { id: "chat", name: "Ask AI", icon: MessageSquare },
  { id: "reports", name: "Reports", icon: FileText },
  { id: "audit", name: "Audit Logs", icon: ClipboardList },
];

export default function DashboardSidebar({
  activeSection = "overview",
  onSectionClick,
}: Props) {
  const navigate = useNavigate();
  const [collapsed, setCollapsed] = useState(false);

  const handleItemClick = (id: string) => {
    if (onSectionClick) {
      onSectionClick(id);
    } else {
      const element = document.getElementById(id);
      if (element) element.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };

  return (
    <div
      className={`h-screen bg-[#0D0D0F] border-r border-white/[0.06] flex flex-col justify-between sticky top-0 transition-all duration-300 ${
        collapsed ? "w-[68px]" : "w-60"
      }`}
    >
      <div>
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

        {/* Nav items */}
        <div className="p-3 space-y-0.5 mt-1">
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
      <div className="p-3 border-t border-white/[0.06] space-y-0.5">
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
          onClick={() => setCollapsed(!collapsed)}
          className="flex items-center justify-center w-full p-2.5 rounded-lg text-zinc-600 hover:text-zinc-400 hover:bg-white/[0.04] transition-all cursor-pointer"
        >
          {collapsed ? <ChevronRight size={16} /> : <ChevronLeft size={16} />}
        </button>
      </div>
    </div>
  );
}