import { Brain } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function Navbar() {
  const navigate = useNavigate();

  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-warmgray-50/80 backdrop-blur-md border-b border-warmgray-100 shadow-sm transition-all duration-300">
      <div className="max-w-7xl mx-auto flex items-center justify-between px-8 py-3">
        {/* Logo */}
        <div 
          onClick={() => navigate("/")}
          className="flex items-center gap-3 cursor-pointer group"
        >
          <div className="bg-gradient-to-br from-terracotta-500 to-terracotta-600 p-2.5 rounded-2xl shadow-md shadow-terracotta-500/10 group-hover:scale-105 transition-transform duration-300">
            <Brain size={22} className="text-white" />
          </div>
          <div className="flex flex-col">
            <span className="text-2xl font-black text-warmgray-900 tracking-tight leading-none group-hover:text-terracotta-600 transition-colors">
              PromptSQL
            </span>
            <span className="text-[10px] text-warmgray-500 font-bold tracking-widest uppercase mt-0.5">
              AI Analytics
            </span>
          </div>
        </div>

        {/* Links */}
        <div className="hidden md:flex items-center gap-8 font-semibold text-sm">
          <a 
            href="#features" 
            className="text-warmgray-500 hover:text-terracotta-500 transition-colors duration-200 cursor-pointer"
          >
            Features
          </a>
          <a 
            onClick={() => navigate("/upload")}
            className="text-warmgray-500 hover:text-terracotta-500 transition-colors duration-200 cursor-pointer"
          >
            Dataset Explorer
          </a>
          <a 
            onClick={() => navigate("/upload")} 
            className="text-warmgray-500 hover:text-terracotta-500 transition-colors duration-200 cursor-pointer"
          >
            AI Assistant
          </a>
        </div>

        {/* CTA Button */}
        <div>
          <button
            onClick={() => navigate("/upload")}
            className="bg-terracotta-500 hover:bg-terracotta-600 text-white font-bold px-6 py-3 rounded-xl transition duration-200 hover:shadow-lg hover:shadow-terracotta-500/15 active:scale-95 text-sm cursor-pointer"
          >
            Upload File
          </button>
        </div>
      </div>
    </nav>
  );
}