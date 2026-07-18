import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Database, Lock, User, ArrowRight, Loader2, AlertCircle } from "lucide-react";
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
      // Store token and user details
      localStorage.setItem("promptsql_token", data.token);
      localStorage.setItem("promptsql_user_id", data.user_id);
      localStorage.setItem("promptsql_username", data.username);
      
      // Clear any previous active dataset so they fetch their own
      sessionStorage.removeItem("dataset");
      
      navigate("/upload");
    } catch (err: any) {
      setError(err.message || "Invalid username or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen bg-[#070708] flex items-center justify-center overflow-hidden font-sans">
      {/* Premium glowing background blurs */}
      <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-violet-600/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 translate-x-1/2 translate-y-1/2 w-96 h-96 bg-emerald-600/10 rounded-full blur-[120px] pointer-events-none" />

      {/* Main card */}
      <div className="w-full max-w-md px-8 py-10 bg-[#0d0d11]/80 backdrop-blur-xl border border-white/[0.06] rounded-3xl shadow-2xl relative z-10">
        <div className="flex flex-col items-center mb-8">
          <div className="p-3 bg-violet-500/10 border border-violet-500/20 rounded-2xl mb-4">
            <Database className="w-8 h-8 text-violet-400 animate-pulse" />
          </div>
          <h2 className="text-2xl font-bold text-white tracking-tight">Welcome back</h2>
          <p className="text-sm text-zinc-400 mt-1.5">Sign in to query your SQL datasets with AI</p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-red-500/10 border border-red-500/20 text-red-200 text-sm rounded-xl flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-red-400 shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Username</label>
            <div className="relative">
              <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Enter your username"
                className="w-full pl-11 pr-4 py-3 bg-[#09090b]/80 border border-white/[0.06] focus:border-violet-500/50 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30 transition-all text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-zinc-400 uppercase tracking-wider mb-2">Password</label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-zinc-500" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="w-full pl-11 pr-4 py-3 bg-[#09090b]/80 border border-white/[0.06] focus:border-violet-500/50 rounded-xl text-white placeholder-zinc-500 focus:outline-none focus:ring-1 focus:ring-violet-500/30 transition-all text-sm"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-3 bg-violet-600 hover:bg-violet-500 text-white rounded-xl text-sm font-semibold shadow-lg shadow-violet-600/10 hover:shadow-violet-500/20 active:scale-[0.98] transition-all flex items-center justify-center gap-2 group disabled:opacity-60 disabled:pointer-events-none"
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

        <div className="mt-8 text-center border-t border-white/[0.04] pt-6">
          <p className="text-sm text-zinc-400">
            Don't have an account?{" "}
            <Link to="/signup" className="text-violet-400 hover:text-violet-300 font-medium transition-colors">
              Create an account
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
