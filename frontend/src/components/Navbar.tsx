import { useState, useEffect, useRef } from "react";
import { Menu, X, LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";

interface NavbarProps {
  onStartQuery?: () => void;
  onOpenAuth?: (mode?: "login" | "signup") => void;
  authRefreshKey?: number;
}

export default function Navbar({ onStartQuery, onOpenAuth, authRefreshKey }: NavbarProps) {
  const navigate = useNavigate();
  const [scrolled, setScrolled] = useState(false);
  const [mobileOpen, setMobileOpen] = useState(false);
  
  // Authentication states
  const [isAuthenticated, setIsAuthenticated] = useState(false);
  const [username, setUsername] = useState("");
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  const profileDropdownRef = useRef<HTMLDivElement>(null);

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
    } else {
      setIsAuthenticated(false);
      setUsername("");
    }

    return () => window.removeEventListener("scroll", handleScroll);
  }, [authRefreshKey]);

  // Click outside and ESC listener to dismiss profile dropdown
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        profileDropdownRef.current &&
        !profileDropdownRef.current.contains(event.target as Node)
      ) {
        setProfileDropdownOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setProfileDropdownOpen(false);
      }
    };

    if (profileDropdownOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
    }

    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [profileDropdownOpen]);

  const handleLogout = () => {
    setProfileDropdownOpen(false);
    localStorage.removeItem("promptsql_token");
    localStorage.removeItem("promptsql_user_id");
    localStorage.removeItem("promptsql_username");
    sessionStorage.clear();
    setIsAuthenticated(false);
    setUsername("");
    navigate("/");
  };

  const initial = (username?.trim()?.[0] || "U").toUpperCase();

  return (
    <nav
      className={`fixed top-0 left-0 right-0 z-50 transition-all duration-300 ${
        scrolled
          ? "bg-[#FFFDFC]/95 backdrop-blur-xl border-b border-[#E8DED3] shadow-sm shadow-[#5A2F59]/5"
          : "bg-transparent"
      }`}
    >
      <div className="max-w-6xl mx-auto flex items-center justify-between px-6 py-4 relative">
        {/* Logo styled in exact PromptSQL brand image style */}
        <div
          onClick={() => navigate("/")}
          className="flex items-center cursor-pointer group z-10"
        >
          <span className="font-black italic tracking-tighter text-xl sm:text-2xl select-none">
            <span className="text-[#152430]">Prompt</span>
            <span className="text-[#0DA4AA]">SQL</span>
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

        {/* Auth Profile / Sign In */}
        <div className="flex items-center gap-3 z-10">
          {isAuthenticated ? (
            /* Logged In: Only First Letter in Capital Avatar Circle */
            <div className="relative" ref={profileDropdownRef}>
              <button
                onClick={() => setProfileDropdownOpen((prev) => !prev)}
                className={`relative w-9 h-9 sm:w-10 sm:h-10 rounded-full flex items-center justify-center font-black text-sm sm:text-base select-none transition-all duration-200 cursor-pointer active:scale-95 focus:outline-none ${
                  profileDropdownOpen
                    ? "bg-[#0DA4AA] text-white ring-2 ring-[#0DA4AA]/40 shadow-md shadow-[#0DA4AA]/30"
                    : "bg-[#152430] hover:bg-[#0DA4AA] text-white border-2 border-[#0DA4AA]/30 hover:border-[#0DA4AA] shadow-sm hover:shadow-md"
                }`}
                title={`Signed in as ${username}`}
                aria-label="User account menu"
                aria-expanded={profileDropdownOpen}
              >
                <span>{initial}</span>
                <span className="absolute bottom-0 right-0 w-2.5 h-2.5 rounded-full bg-emerald-500 border-2 border-[#FFFDFC]" />
              </button>

              {/* Floating Dropdown showing Full Name along with Logout Button */}
              {profileDropdownOpen && (
                <div className="absolute right-0 mt-2.5 w-60 bg-white/98 backdrop-blur-xl border border-[#E8DED3] rounded-2xl shadow-xl shadow-[#152430]/15 p-3.5 z-50 animate-in fade-in zoom-in-95 duration-150">
                  {/* Full Name Display */}
                  <div className="flex items-center gap-3 p-2.5 bg-[#152430]/5 rounded-xl border border-[#152430]/10 mb-2.5">
                    <div className="w-9 h-9 rounded-full bg-[#0DA4AA] text-white font-black text-sm flex items-center justify-center shrink-0 shadow-sm shadow-[#0DA4AA]/25">
                      {initial}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-[10px] uppercase tracking-wider font-bold text-[#6F6A67] leading-none mb-1">
                        Signed in
                      </p>
                      <p className="text-sm font-bold text-[#152430] truncate" title={username}>
                        {username}
                      </p>
                      <div className="flex items-center gap-1.5 mt-1">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
                        <span className="text-[10px] font-semibold text-emerald-600">Online</span>
                      </div>
                    </div>
                  </div>

                  {/* Quick Link to Workspace */}
                  <button
                    onClick={() => {
                      setProfileDropdownOpen(false);
                      if (onStartQuery) {
                        onStartQuery();
                      } else {
                        navigate("/upload");
                      }
                    }}
                    className="w-full flex items-center justify-between px-3 py-2 text-xs font-semibold text-[#152430] hover:text-[#0DA4AA] hover:bg-[#0DA4AA]/8 rounded-xl transition-all cursor-pointer group mb-1.5"
                  >
                    <span className="flex items-center gap-2">
                      <span className="w-2 h-2 rounded-full bg-[#0DA4AA]" />
                      <span>Open Workspace</span>
                    </span>
                    <span className="text-[11px] text-[#6F6A67] group-hover:text-[#0DA4AA] font-medium transition-transform group-hover:translate-x-0.5">
                      &rarr;
                    </span>
                  </button>

                  <div className="h-px bg-[#E8DED3] my-2" />

                  {/* Logout Button */}
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center justify-center gap-2 py-2 px-3 bg-[#FF4742] hover:bg-[#E93B36] text-white rounded-xl text-xs font-bold shadow-md shadow-[#FF4742]/20 hover:shadow-lg hover:shadow-[#FF4742]/35 transition-all duration-200 cursor-pointer active:scale-95"
                  >
                    <LogOut size={14} className="shrink-0" />
                    <span>Logout</span>
                  </button>
                </div>
              )}
            </div>
          ) : (
            /* Video 2 Style: Sign In Button with Liquid Wave Downward Wipe */
            <button
              onClick={() => {
                if (onOpenAuth) {
                  onOpenAuth("login");
                } else {
                  navigate("/login");
                }
              }}
              className="group relative overflow-hidden bg-[#0DA4AA] border border-[#0B9297] text-white font-semibold px-6 py-2 rounded-xl text-sm shadow-md shadow-[#0DA4AA]/25 hover:shadow-lg hover:shadow-black/10 transition-all duration-300 cursor-pointer active:scale-95"
            >
              {/* Liquid curved wave wipe */}
              <span className="absolute -top-[50%] -left-[10%] w-[120%] h-[200%] bg-[#FFFDFC] rounded-b-[50%] -translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out pointer-events-none" />
              <span className="relative z-10 transition-colors duration-300 group-hover:text-[#152430]">
                Sign In
              </span>
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
              <div className="flex items-center gap-3 px-3 py-2 bg-[#152430]/5 rounded-xl border border-[#152430]/10">
                <div className="w-8 h-8 rounded-full bg-[#0DA4AA] text-white font-black text-xs flex items-center justify-center shrink-0">
                  {initial}
                </div>
                <div className="min-w-0 flex-1">
                  <p className="text-[10px] text-[#6F6A67] font-medium leading-none">Signed in as</p>
                  <p className="text-xs font-bold text-[#152430] truncate">{username}</p>
                </div>
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
                className="w-full text-center px-4 py-2 text-xs text-white bg-[#FF4742] hover:bg-[#E93B36] rounded-xl font-semibold shadow-md shadow-[#FF4742]/20 transition flex items-center justify-center gap-2"
              >
                <LogOut size={14} />
                Logout
              </button>
            </div>
          ) : (
            <button
              onClick={() => {
                setMobileOpen(false);
                if (onOpenAuth) {
                  onOpenAuth("login");
                } else {
                  navigate("/login");
                }
              }}
              className="group relative overflow-hidden w-full mt-2 bg-[#0DA4AA] border border-[#0B9297] text-[#FFFDFC] font-semibold px-4 py-2.5 rounded-xl text-sm cursor-pointer shadow-md shadow-[#0DA4AA]/20"
            >
              <span className="absolute -top-[50%] -left-[10%] w-[120%] h-[200%] bg-[#FFFDFC] rounded-b-[50%] -translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out pointer-events-none" />
              <span className="relative z-10 transition-colors duration-300 group-hover:text-[#152430]">
                Sign In
              </span>
            </button>
          )}
        </div>
      )}
    </nav>
  );
}
