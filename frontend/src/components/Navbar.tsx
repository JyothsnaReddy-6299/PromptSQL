import { useState, useEffect } from "react";
import { Brain, Menu, X } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function Navbar() {
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll);
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-[#09090B]/90 backdrop-blur-xl border-b border-white/[0.06] shadow-2xl shadow-black/20"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-4">
        {/* Logo */}
        <div
          onClick={() => navigate("/")}
          className="flex items-center gap-2.5 cursor-pointer group"
        >
          <div className="relative">
            <div className="w-8 h-8 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-lg flex items-center justify-center shadow-lg shadow-indigo-500/25 group-hover:shadow-indigo-500/40 transition-shadow duration-300">
              <Brain size={16} className="text-white" />
            </div>
            <div className="absolute -inset-0.5 bg-gradient-to-br from-indigo-500 to-violet-600 rounded-lg blur opacity-0 group-hover:opacity-30 transition-opacity duration-300 -z-10" />
          </div>
          <span className="text-lg font-bold text-white tracking-tight group-hover:text-indigo-300 transition-colors duration-200">
            PromptSQL
          </span>
        </div>

        {/* Nav Links */}
        <div className="hidden md:flex items-center gap-1">
          {[
            { name: "Features", href: "#features" },
            { name: "How it works", href: "#how-it-works" }
          ].map((item) => (
            <a
              key={item.name}
              href={item.href}
              className="px-4 py-2 text-sm text-zinc-400 hover:text-white rounded-lg hover:bg-white/[0.05] transition-all duration-200 cursor-pointer"
            >
              {item.name}
            </a>
          ))}
        </div>

        {/* CTA */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => navigate("/upload")}
            className="relative group bg-white text-zinc-900 hover:bg-zinc-100 font-semibold px-4 py-2 rounded-lg text-sm transition-all duration-200 cursor-pointer shadow-sm"
          >
            <span className="relative z-10">Get Started</span>
          </button>
          <button
            className="md:hidden text-zinc-400 hover:text-white"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden bg-[#111113]/95 backdrop-blur-xl border-b border-white/[0.06] px-6 pb-4 space-y-1">
          {[
            { name: "Features", href: "#features" },
            { name: "How it works", href: "#how-it-works" }
          ].map((item) => (
            <a
              key={item.name}
              href={item.href}
              className="block px-4 py-3 text-sm text-zinc-400 hover:text-white hover:bg-white/[0.05] rounded-lg transition"
              onClick={() => setMobileOpen(false)}
            >
              {item.name}
            </a>
          ))}
          <button
            onClick={() => navigate("/upload")}
            className="w-full mt-2 bg-white text-zinc-900 font-semibold px-4 py-2.5 rounded-lg text-sm cursor-pointer"
          >
            Get Started Free
          </button>
        </div>
      )}
    </nav>
  );
}