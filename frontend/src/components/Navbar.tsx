import { useState, useEffect } from "react";
import { Brain, Menu, X, LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function Navbar() {
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  
  // Authentication states
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState("");
  const [dropdownOpen, setDropdownOpen] = useState(false);

  useEffect(() => {
    const handleScroll = () => setScrolled(window.scrollY > 20);
    window.addEventListener("scroll", handleScroll);

    // Retrieve authentication status
    const token = localStorage.getItem("promptsql_token");
    const storedUsername = localStorage.getItem("promptsql_username") || "";
    if (token) {
      setIsAuthenticated(true);
      setUsername(storedUsername);
    }

    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  const handleLogout = () => {
    localStorage.removeItem("promptsql_token");
    localStorage.removeItem("promptsql_user_id");
    localStorage.removeItem("promptsql_username");
    sessionStorage.clear();
    setIsAuthenticated(false);
    setUsername("");
    setDropdownOpen(false);
    navigate("/");
  };

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

        {/* Auth CTA & Profile Avatar */}
        <div className="flex items-center gap-3">
          {isAuthenticated ? (
            <div className="relative">
              <button
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className="w-9 h-9 rounded-full bg-gradient-to-tr from-violet-600 to-indigo-600 text-white font-bold text-sm flex items-center justify-center border border-white/10 hover:border-violet-500/50 shadow-md shadow-violet-600/10 cursor-pointer transition-all active:scale-95"
                title="Profile Menu"
              >
                {username ? username.charAt(0).toUpperCase() : "U"}
              </button>
              
              {dropdownOpen && (
                <div className="absolute right-0 mt-2.5 w-48 bg-[#0D0D11]/95 backdrop-blur-xl border border-white/[0.08] rounded-xl shadow-2xl py-1.5 z-50 text-left">
                  <div className="px-4 py-2 border-b border-white/[0.04] text-xs text-zinc-400">
                    Signed in as <span className="font-semibold text-white block truncate">{username}</span>
                  </div>
                  <button
                    onClick={() => {
                      setDropdownOpen(false);
                      navigate("/upload");
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-zinc-300 hover:text-white hover:bg-white/[0.05] transition-colors cursor-pointer"
                  >
                    Go to Workspace
                  </button>
                  <button
                    onClick={handleLogout}
                    className="w-full text-left px-4 py-2 text-sm text-red-400 hover:text-red-300 hover:bg-red-500/10 transition-colors cursor-pointer border-t border-white/[0.04] mt-1.5 pt-2 flex items-center gap-2"
                  >
                    <LogOut size={14} />
                    Logout
                  </button>
                </div>
              )}
            </div>
          ) : (
            <button
              onClick={() => navigate("/login")}
              className="relative group bg-white text-zinc-900 hover:bg-zinc-100 font-semibold px-5 py-2 rounded-lg text-sm transition-all duration-200 cursor-pointer shadow-sm"
            >
              <span className="relative z-10">Sign In</span>
            </button>
          )}

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
          
          {isAuthenticated ? (
            <div className="mt-3 border-t border-white/[0.06] pt-3 space-y-2">
              <div className="px-4 text-xs text-zinc-500">
                Signed in as <span className="text-zinc-300 font-semibold">{username}</span>
              </div>
              <button
                onClick={() => {
                  setMobileOpen(false);
                  navigate("/upload");
                }}
                className="w-full text-left px-4 py-2.5 text-sm text-zinc-300 hover:text-white hover:bg-white/[0.05] rounded-lg transition"
              >
                Go to Workspace
              </button>
              <button
                onClick={() => {
                  setMobileOpen(false);
                  handleLogout();
                }}
                className="w-full text-left px-4 py-2.5 text-sm text-red-400 hover:bg-red-500/10 rounded-lg transition flex items-center gap-2"
              >
                <LogOut size={14} />
                Logout
              </button>
            </div>
          ) : (
            <button
              onClick={() => {
                setMobileOpen(false);
                navigate("/login");
              }}
              className="w-full mt-2 bg-white text-zinc-900 font-semibold px-4 py-2.5 rounded-lg text-sm cursor-pointer"
            >
              Sign In
            </button>
          )}
        </div>
      )}
    </nav>
  );
}