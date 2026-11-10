import React, { useState, useEffect } from "react";
import { createPortal } from "react-dom";
import { X, Lock, User, ArrowRight, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { login, signup } from "../services/api";

interface AuthModalProps {
  isOpen: boolean;
  initialMode?: "login" | "signup";
  onClose: () => void;
  onSuccess?: () => void;
}

const PROMPTSQL_SESSION_KEYS = [
  "dataset",
  "promptsql_dataset",
  "promptsql_active_dataset",
  "promptsql_table",
  "promptsql_active_table",
  "promptsql_temp_query",
];

function clearPromptSQLSessionState() {
  for (const key of PROMPTSQL_SESSION_KEYS) {
    sessionStorage.removeItem(key);
  }
}

export default function AuthModal({
  isOpen,
  initialMode = "login",
  onClose,
  onSuccess,
}: AuthModalProps) {
  const [mode, setMode] = useState<"login" | "signup">(initialMode);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [successMsg, setSuccessMsg] = useState("");

  // Keep mode synced with initialMode when opened
  useEffect(() => {
    if (isOpen) {
      setMode(initialMode);
      setError("");
      setSuccessMsg("");
      setUsername("");
      setPassword("");
      setConfirmPassword("");
    }
  }, [isOpen, initialMode]);

  // ESC key listener to dismiss
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("Please fill in all fields.");
      return;
    }

    if (mode === "signup") {
      if (!confirmPassword.trim()) {
        setError("Please confirm your password.");
        return;
      }
      if (password !== confirmPassword) {
        setError("Passwords do not match.");
        return;
      }
      if (password.length < 12) {
        setError("Password must be at least 12 characters long.");
        return;
      }
    }

    setLoading(true);
    setError("");
    setSuccessMsg("");

    try {
      if (mode === "login") {
        const data = await login(username, password);
        localStorage.setItem("promptsql_token", data.token);
        localStorage.setItem("promptsql_user_id", data.user_id);
        localStorage.setItem("promptsql_username", data.username);
        clearPromptSQLSessionState();
        if (onSuccess) onSuccess();
        onClose();
      } else {
        const data = await signup(username, password);
        setSuccessMsg("Account created successfully!");
        localStorage.setItem("promptsql_token", data.token);
        localStorage.setItem("promptsql_user_id", data.user_id);
        localStorage.setItem("promptsql_username", data.username);
        clearPromptSQLSessionState();
        setTimeout(() => {
          if (onSuccess) onSuccess();
          onClose();
        }, 800);
      }
    } catch (err: any) {
      setError(
        err.message ||
          (mode === "login"
            ? "Invalid username or password. Please try again."
            : "Failed to create account. Username might be taken.")
      );
    } finally {
      setLoading(false);
    }
  };

  const switchMode = (newMode: "login" | "signup") => {
    setMode(newMode);
    setError("");
    setSuccessMsg("");
  };

  return createPortal(
    <div
      className="fixed inset-0 z-[9999] flex items-center justify-center p-4 bg-[#152430]/50 backdrop-blur-md transition-all duration-300"
      onClick={onClose}
    >
      {/* Modal Card - Compact and Proportionate */}
      <div
        className="w-full max-w-[360px] bg-[#FFFDFC] border-2 border-[#E8DED3] rounded-3xl shadow-2xl shadow-[#152430]/25 relative z-10 p-5 sm:p-6 my-auto transform transition-all duration-300 animate-in fade-in zoom-in-95"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Close Button */}
        <button
          onClick={onClose}
          className="absolute top-3.5 right-3.5 w-7 h-7 rounded-full bg-[#F7F2EC] hover:bg-[#E8DED3] text-[#6F6A67] hover:text-[#241C20] flex items-center justify-center transition-colors cursor-pointer"
          aria-label="Close"
        >
          <X size={15} />
        </button>

        {/* Brand Header styled in exact PromptSQL logo style */}
        <div className="flex flex-col items-center mb-4 text-center">
          <div className="mb-1.5">
            <span className="font-black italic tracking-tighter text-xl sm:text-2xl select-none">
              <span className="text-[#152430]">Prompt</span>
              <span className="text-[#0DA4AA]">SQL</span>
            </span>
          </div>
          <h2 className="text-lg font-bold text-[#241C20] tracking-tight">
            {mode === "login" ? "Sign In" : "Create an account"}
          </h2>
        </div>

        {/* Error Notification */}
        {error && (
          <div className="mb-3.5 p-2.5 bg-[#D95D39]/8 border border-[#D95D39]/20 text-[#D95D39] text-xs rounded-xl flex items-start gap-2">
            <AlertCircle className="w-4 h-4 text-[#D95D39] shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {/* Success Notification */}
        {successMsg && (
          <div className="mb-3.5 p-2.5 bg-emerald-500/10 border border-emerald-500/25 text-emerald-700 text-xs rounded-xl flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{successMsg}</span>
          </div>
        )}

        {/* Auth Form */}
        <form onSubmit={handleSubmit} className="space-y-3">
          <div>
            <label className="block text-[10px] font-semibold text-[#6F6A67] uppercase tracking-wider mb-1">
              Username
            </label>
            <div className="relative">
              <User className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#B0A79E]" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                autoFocus
                className="w-full pl-9 pr-3.5 py-2 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#0DA4AA] rounded-xl text-[#241C20] placeholder-[#B0A79E] focus:outline-none focus:ring-2 focus:ring-[#0DA4AA]/15 transition-all text-xs"
              />
            </div>
          </div>

          <div>
            <label className="block text-[10px] font-semibold text-[#6F6A67] uppercase tracking-wider mb-1">
              Password
            </label>
            <div className="relative">
              <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#B0A79E]" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-9 pr-3.5 py-2 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#0DA4AA] rounded-xl text-[#241C20] placeholder-[#B0A79E] focus:outline-none focus:ring-2 focus:ring-[#0DA4AA]/15 transition-all text-xs"
              />
            </div>
          </div>

          {mode === "signup" && (
            <div>
              <label className="block text-[10px] font-semibold text-[#6F6A67] uppercase tracking-wider mb-1">
                Confirm Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-[#B0A79E]" />
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  placeholder="Confirm your password"
                  className="w-full pl-9 pr-3.5 py-2 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#0DA4AA] rounded-xl text-[#241C20] placeholder-[#B0A79E] focus:outline-none focus:ring-2 focus:ring-[#0DA4AA]/15 transition-all text-xs"
                />
              </div>
            </div>
          )}

          {/* Video 2 Style Liquid Curved Wave Wipe Button */}
          <button
            type="submit"
            disabled={loading}
            className="group relative overflow-hidden w-full mt-1.5 py-2.5 bg-[#0DA4AA] border border-[#0B9297] text-[#FFFDFC] rounded-xl text-xs font-bold shadow-md shadow-[#0DA4AA]/25 hover:shadow-lg hover:shadow-black/10 active:scale-[0.98] transition-all flex items-center justify-center gap-2 disabled:opacity-60 disabled:pointer-events-none cursor-pointer"
          >
            {/* Liquid curved wave wipe */}
            <span className="absolute -top-[50%] -left-[10%] w-[120%] h-[200%] bg-[#FFFDFC] rounded-b-[50%] -translate-y-full group-hover:translate-y-0 transition-transform duration-300 ease-out pointer-events-none" />
            <span className="relative z-10 flex items-center justify-center gap-2 transition-colors duration-300 group-hover:text-[#152430]">
              {loading ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  <span>{mode === "login" ? "Signing in..." : "Creating account..."}</span>
                </>
              ) : (
                <>
                  <span>{mode === "login" ? "Sign In" : "Create Account"}</span>
                  <ArrowRight className="w-3.5 h-3.5 group-hover:translate-x-1 transition-transform" />
                </>
              )}
            </span>
          </button>
        </form>

        {/* Switch Mode Footer */}
        <div className="mt-4 text-center border-t border-[#E8DED3] pt-3">
          {mode === "login" ? (
            <p className="text-xs text-[#6F6A67]">
              Don't have an account?{" "}
              <button
                type="button"
                onClick={() => switchMode("signup")}
                className="text-[#0DA4AA] hover:text-[#0B9297] font-semibold transition-colors cursor-pointer"
              >
                Create an account
              </button>
            </p>
          ) : (
            <p className="text-xs text-[#6F6A67]">
              Already have an account?{" "}
              <button
                type="button"
                onClick={() => switchMode("login")}
                className="text-[#0DA4AA] hover:text-[#0B9297] font-semibold transition-colors cursor-pointer"
              >
                Sign in
              </button>
            </p>
          )}
        </div>
      </div>
    </div>,
    document.body
  );
}
