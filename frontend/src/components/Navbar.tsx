import { useState, useEffect } from "react";
import { Brain, Menu, X, LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";

interface NavbarProps {
  onStartQuery?: () => void;
}

export default function Navbar({ onStartQuery }: NavbarProps) {
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

    // Retrieve authentication status and check expiration (24h logout safety)
    const token = localStorage.getItem("promptsql_token");
    const storedUsername = localStorage.getItem("promptsql_username") || "";

    const isExpired = (t: string | null) => {
      if (!t) return true;
      try {
        const parts = t.split(".");
        if (parts.length !== 3) return true;
        const payload = JSON.parse(atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")));
        if (typeof payload.exp !== "number") return false;
        return Math.floor(Date.now() / 1000) >= payload.exp;
      } catch (e) {
        return true;
      }
    };

    if (token && !isExpired(token)) {
      setIsAuthenticated(true);
      setUsername(storedUsername);
    } else if (token) {
      // Clear expired credentials
      localStorage.removeItem("promptsql_token");
      localStorage.removeItem("promptsql_user_id");
      localStorage.removeItem("promptsql_username");
      sessionStorage.clear();
      setIsAuthenticated(false);
      setUsername("");
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
          ? "bg-[#FFFDFC]/95 backdrop-blur-xl border-b border-[#E8DED3] shadow-sm shadow-[#5A2F59]/5"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-4 relative">
        {/* Logo */}
        <div
          onClick={() => navigate("/")}
          className="flex items-center gap-2.5 cursor-pointer group z-10"
        >
          <div className="relative">
            <div className="w-8 h-8 bg-[#5A2F59] rounded-lg flex items-center justify-center shadow-md shadow-[#5A2F59]/20 group-hover:shadow-[#5A2F59]/35 transition-shadow duration-300">
              <Brain size={16} className="text-[#BDA37A]" />
            </div>
            <div className="absolute -inset-0.5 bg-[#5A2F59] rounded-lg blur opacity-0 group-hover:opacity-20 transition-opacity duration-300 -z-10" />
          </div>
          <span className="text-lg font-bold text-[#241C20] tracking-tight group-hover:text-[#5A2F59] transition-colors duration-200">
            PromptSQL
          </span>
        </div>

        {/* Nav Links */}
        <div className="hidden md:flex absolute left-1/2 -translate-x-1/2 items-center gap-1">
          {[
            { name: "Features", href: "#features" },
            { name: "How it works", href: "#how-it-works" }
          ].map((item) => (
            <a
              key={item.name}
              href={item.href}
              className="px-4 py-2 text-sm text-[#6F6A67] hover:text-[#241C20] rounded-lg hover:bg-[#5A2F59]/6 transition-all duration-200 cursor-pointer"
            >
              {item.name}
            </a>
          ))}
        </div>

        {/* Auth CTA & Profile Avatar */}
        <div className="flex items-center gap-3 z-10">
          {isAuthenticated ? (
            <div className="relative">
              <button
                onClick={() => setDropdownOpen(!dropdownOpen)}
                className="w-9 h-9 rounded-full bg-[#5A2F59] text-[#FFFDFC] font-bold text-sm flex items-center justify-center border-2 border-[#BDA37A]/40 hover:border-[#BDA37A]/70 shadow-md shadow-[#5A2F59]/20 cursor-pointer transition-all active:scale-95"
                title="Profile Menu"
              >
                {username ? username.charAt(0).toUpperCase() : "U"}
              </button>
              
              {dropdownOpen && (
                <div className="absolute right-0 mt-2.5 w-48 bg-[#FFFDFC] backdrop-blur-xl border border-[#E8DED3] rounded-xl shadow-xl shadow-[#5A2F59]/8 py-1.5 z-50 text-left">
                  <div className="px-4 py-2 border-b border-[#E8DED3] text-xs text-[#6F6A67]">
                    Signed in as <span className="font-semibold text-[#241C20] block truncate">{username}</span>
                  </div>
                  <button
                    onClick={() => {
                      setDropdownOpen(false);
                      if (onStartQuery) {
                        onStartQuery();
                      } else {
                        navigate("/upload");
                      }
                    }}
                    className="w-full text-left px-4 py-2 text-sm text-[#6F6A67] hover:text-[#241C20] hover:bg-[#5A2F59]/6 transition-colors cursor-pointer"
                  >
                    Go to Workspace
                  </button>
                  <button
                    onClick={handleLogout}
                    className="w-full text-left px-4 py-2 text-sm text-[#D95D39] hover:text-[#C04A28] hover:bg-[#D95D39]/8 transition-colors cursor-pointer border-t border-[#E8DED3] mt-1.5 pt-2 flex items-center gap-2"
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
              className="relative group bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] font-semibold px-5 py-2 rounded-lg text-sm transition-all duration-200 cursor-pointer shadow-sm shadow-[#5A2F59]/20"
            >
              <span className="relative z-10">Sign In</span>
            </button>
          )}

          <button
            className="md:hidden text-[#6F6A67] hover:text-[#241C20]"
            onClick={() => setMobileOpen(!mobileOpen)}
          >
            {mobileOpen ? <X size={20} /> : <Menu size={20} />}
          </button>
        </div>
      </div>

      {/* Mobile menu */}
      {mobileOpen && (
        <div className="md:hidden bg-[#FFFDFC]/95 backdrop-blur-xl border-b border-[#E8DED3] px-6 pb-4 space-y-1">
          {[
            { name: "Features", href: "#features" },
            { name: "How it works", href: "#how-it-works" }
          ].map((item) => (
            <a
              key={item.name}
              href={item.href}
              className="block px-4 py-3 text-sm text-[#6F6A67] hover:text-[#241C20] hover:bg-[#5A2F59]/6 rounded-lg transition"
              onClick={() => setMobileOpen(false)}
            >
              {item.name}
            </a>
          ))}
          
          {isAuthenticated ? (
            <div className="mt-3 border-t border-[#E8DED3] pt-3 space-y-2">
              <div className="px-4 text-xs text-[#6F6A67]">
                Signed in as <span className="text-[#241C20] font-semibold">{username}</span>
              </div>
              <button
                onClick={() => {
                  setMobileOpen(false);
                  if (onStartQuery) {
                    onStartQuery();
                  } else {
                    navigate("/upload");
                  }
                }}
                className="w-full text-left px-4 py-2.5 text-sm text-[#6F6A67] hover:text-[#241C20] hover:bg-[#5A2F59]/6 rounded-lg transition"
              >
                Go to Workspace
              </button>
              <button
                onClick={() => {
                  setMobileOpen(false);
                  handleLogout();
                }}
                className="w-full text-left px-4 py-2.5 text-sm text-[#D95D39] hover:bg-[#D95D39]/8 rounded-lg transition flex items-center gap-2"
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
              className="w-full mt-2 bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] font-semibold px-4 py-2.5 rounded-lg text-sm cursor-pointer"
            >
              Sign In
            </button>
          )}
        </div>
      )}
    </nav>
  );
}