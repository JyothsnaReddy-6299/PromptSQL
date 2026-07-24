import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Brain, Lock, User, ArrowRight, Loader2, AlertCircle } from "lucide-react";
import { login } from "../services/api";

export default function LoginPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim()) {
      setError("Please fill in all fields.");
      return;
    }
    setLoading(true);
    setError("");

    try {
      const data = await login(username, password);
      localStorage.setItem("promptsql_token", data.token);
      localStorage.setItem("promptsql_user_id", data.user_id);
      localStorage.setItem("promptsql_username", data.username);
      sessionStorage.removeItem("dataset");
      navigate("/");
    } catch (err: any) {
      setError(err.message || "Invalid username or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative h-screen bg-[#F7F2EC] flex items-center justify-center p-4 overflow-hidden font-sans">
      {/* Warm background glows */}
      <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-[#5A2F59]/8 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 translate-x-1/2 translate-y-1/2 w-96 h-96 bg-[#BDA37A]/10 rounded-full blur-[120px] pointer-events-none" />

      {/* Main card */}
      <div className="w-full max-w-md px-7 py-7 bg-[#FFFDFC] border-2 border-[#E8DED3] rounded-3xl shadow-xl shadow-[#5A2F59]/8 relative z-10 my-auto">
        <div className="flex flex-col items-center mb-6">
          <div className="p-2.5 bg-[#5A2F59] border border-[#BDA37A]/20 rounded-2xl mb-3 shadow-md shadow-[#5A2F59]/20">
            <Brain className="w-7 h-7 text-[#BDA37A]" />
          </div>
          <h2 className="text-2xl font-bold text-[#241C20] tracking-tight">Welcome back</h2>
          <p className="text-xs text-[#6F6A67] mt-1">Sign in to query your SQL datasets with AI</p>
        </div>

        {error && (
          <div className="mb-4 p-3 bg-[#D95D39]/8 border border-[#D95D39]/20 text-[#D95D39] text-xs rounded-xl flex items-start gap-2.5">
            <AlertCircle className="w-4 h-4 text-[#D95D39] shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-[11px] font-semibold text-[#6F6A67] uppercase tracking-wider mb-1">Username</label>
            <div className="relative">
              <User className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#B0A79E]" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                className="w-full pl-10 pr-4 py-2.5 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#5A2F59]/50 rounded-xl text-[#241C20] placeholder-[#B0A79E] focus:outline-none focus:ring-2 focus:ring-[#5A2F59]/15 transition-all text-xs"
              />
            </div>
          </div>

          <div>
            <label className="block text-[11px] font-semibold text-[#6F6A67] uppercase tracking-wider mb-1">Password</label>
            <div className="relative">
              <Lock className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-[#B0A79E]" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-10 pr-4 py-2.5 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#5A2F59]/50 rounded-xl text-[#241C20] placeholder-[#B0A79E] focus:outline-none focus:ring-2 focus:ring-[#5A2F59]/15 transition-all text-xs"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-1 py-2.5 bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] rounded-xl text-xs font-semibold shadow-md shadow-[#5A2F59]/20 hover:shadow-[#5A2F59]/30 active:scale-[0.98] transition-all flex items-center justify-center gap-2 group disabled:opacity-60 disabled:pointer-events-none cursor-pointer"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Signing in...
              </>
            ) : (
              <>
                Sign in
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </>
            )}
          </button>
        </form>

        <div className="mt-6 text-center border-t border-[#E8DED3] pt-4">
          <p className="text-xs text-[#6F6A67]">
            Don't have an account?{" "}
            <Link to="/signup" className="text-[#5A2F59] hover:text-[#4A2549] font-semibold transition-colors">
              Create an account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
