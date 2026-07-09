import { Brain } from "lucide-react";

export default function Footer() {
  const currentYear = new Date().getFullYear();

  return (
    <footer className="bg-white border-t border-warmgray-100 py-12">
      <div className="max-w-7xl mx-auto px-8 flex flex-col md:flex-row items-center justify-between gap-6">
        {/* Brand */}
        <div className="flex items-center gap-2.5">
          <div className="bg-gradient-to-br from-terracotta-500 to-terracotta-600 p-2 rounded-xl text-white">
            <Brain size={16} />
          </div>
          <span className="font-extrabold text-warmgray-900 text-base tracking-tight animate-pulse">
            PromptSQL
          </span>
        </div>

        {/* Text */}
        <p className="text-xs font-semibold text-warmgray-400 text-center md:text-left">
          &copy; {currentYear} PromptSQL. All rights reserved. Built with advanced agentic LLM mapping.
        </p>

        {/* Links */}
        <div className="flex gap-6 text-xs font-bold text-warmgray-400">
          <a className="hover:text-terracotta-500 cursor-pointer transition">Privacy Policy</a>
          <a className="hover:text-terracotta-500 cursor-pointer transition">Terms of Service</a>
        </div>
      </div>
    </footer>
  );
}
