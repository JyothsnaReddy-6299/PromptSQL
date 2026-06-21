import { Bell, User } from "lucide-react";

export default function DashboardNavbar() {
  return (
    <div className="bg-white rounded-2xl shadow-sm px-6 py-4 flex items-center justify-between">

      {/* Left Side */}
      <div>
        <h1 className="text-2xl font-bold text-gray-800">
          Dashboard
        </h1>

        <p className="text-sm text-gray-500">
          customers.csv
        </p>
      </div>

      {/* Right Side */}
      <div className="flex items-center gap-4">

        <button className="p-2 rounded-full hover:bg-blue-50 transition">
          <Bell size={22} className="text-blue-500" />
        </button>

        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
          <User size={20} className="text-blue-600" />
        </div>

      </div>

    </div>
  );
}