import {
  LayoutDashboard,
  Database,
  BarChart3,
  Brain,
  MessageSquare,
  Settings
} from "lucide-react";

const menuItems = [
  { name: "Dashboard", icon: LayoutDashboard },
  { name: "Dataset Summary", icon: Database },
  { name: "Visualizations", icon: BarChart3 },
  { name: "AI Insights", icon: Brain },
  { name: "Chat with Data", icon: MessageSquare },
  { name: "Settings", icon: Settings }
];

export default function DashboardSidebar() {
  return (
    <div className="w-64 h-screen bg-white border-r border-blue-100 p-6">

      <h1 className="text-2xl font-bold text-blue-600 mb-10">
        AI Analytics
      </h1>

      <div className="space-y-3">
        {menuItems.map((item) => {
          const Icon = item.icon;

          return (
            <button
              key={item.name}
              className="
                flex
                items-center
                gap-3
                w-full
                p-3
                rounded-xl
                hover:bg-blue-50
                transition
              "
            >
              <Icon size={20} className="text-blue-500" />

              <span className="text-gray-700">
                {item.name}
              </span>
            </button>
          );
        })}
      </div>

    </div>
  );
}