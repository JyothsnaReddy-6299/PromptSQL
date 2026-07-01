import { Brain } from "lucide-react";

export default function Navbar() {
  return (
    <nav className="fixed top-0 left-0 right-0 z-50 bg-white/80 backdrop-blur-lg border-b border-slate-200 shadow-sm">

      <div className="max-w-7xl mx-auto flex items-center justify-between px-8 py-4">

        {/* Logo */}
        <div className="flex items-center gap-3">

          <div className="bg-gradient-to-r from-blue-600 to-cyan-500 p-3 rounded-xl">
            <Brain size={22} className="text-white" />
          </div>

          <h1 className="text-3xl font-bold text-slate-800">
            PromptSQL
          </h1>

        </div>


        {/* Links */}
        <div className="flex items-center gap-10">

          <a className="text-slate-600 hover:text-blue-600 transition cursor-pointer">
            Features
          </a>

          <a className="text-slate-600 hover:text-blue-600 transition cursor-pointer">
            Upload
          </a>

          <a className="text-slate-600 hover:text-blue-600 transition cursor-pointer">
            About
          </a>

        </div>

      </div>

    </nav>
  );
}