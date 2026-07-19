import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Brain, Lock, User, ArrowRight, Loader2, AlertCircle, CheckCircle2 } from "lucide-react";
import { signup } from "../services/api";

export default function SignupPage() {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const navigate = useNavigate();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password.trim() || !confirmPassword.trim()) {
      setError("Please fill in all fields.");
      return;
    }
    if (password !== confirmPassword) {
      setError("Passwords do not match.");
      return;
    }
    if (password.length < 6) {
      setError("Password must be at least 6 characters long.");
      return;
    }
    setLoading(true);
    setError("");
    setSuccess("");

    try {
      const data = await signup(username, password);
      setSuccess("Account created successfully!");
      localStorage.setItem("promptsql_token", data.token);
      localStorage.setItem("promptsql_user_id", data.user_id);
      localStorage.setItem("promptsql_username", data.username);
      sessionStorage.removeItem("dataset");
      setTimeout(() => {
        navigate("/upload");
      }, 1000);
    } catch (err: any) {
      setError(err.message || "Failed to create account. Username might be taken.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="relative min-h-screen bg-[#F7F2EC] flex items-center justify-center overflow-hidden font-sans">
      {/* Warm background glows */}
      <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 w-96 h-96 bg-[#5A2F59]/8 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 translate-x-1/2 translate-y-1/2 w-96 h-96 bg-[#BDA37A]/10 rounded-full blur-[120px] pointer-events-none" />

      {/* Main card */}
      <div className="w-full max-w-md px-8 py-10 bg-[#FFFDFC] border border-[#E8DED3] rounded-3xl shadow-xl shadow-[#5A2F59]/5 relative z-10">
        <div className="flex flex-col items-center mb-8">
          <div className="p-3 bg-[#5A2F59] border border-[#BDA37A]/20 rounded-2xl mb-4 shadow-md shadow-[#5A2F59]/20">
            <Brain className="w-8 h-8 text-[#BDA37A]" />
          </div>
          <h2 className="text-2xl font-bold text-[#241C20] tracking-tight">Create an account</h2>
          <p className="text-sm text-[#6F6A67] mt-1.5 font-sans">Start analyzing your datasets with SQL and AI</p>
        </div>

        {error && (
          <div className="mb-6 p-4 bg-[#D95D39]/8 border border-[#D95D39]/20 text-[#D95D39] text-sm rounded-xl flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-[#D95D39] shrink-0 mt-0.5" />
            <span>{error}</span>
          </div>
        )}

        {success && (
          <div className="mb-6 p-4 bg-[#3E8E5B]/8 border border-[#3E8E5B]/20 text-[#3E8E5B] text-sm rounded-xl flex items-start gap-3">
            <CheckCircle2 className="w-5 h-5 text-[#3E8E5B] shrink-0 mt-0.5" />
            <span>{success} Redirecting to workspace...</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-xs font-semibold text-[#6F6A67] uppercase tracking-wider mb-2">Username</label>
            <div className="relative">
              <User className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#B0A79E]" />
              <input
                type="text"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                placeholder="Choose a username"
                className="w-full pl-11 pr-4 py-3 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#5A2F59]/50 rounded-xl text-[#241C20] placeholder-[#B0A79E] focus:outline-none focus:ring-2 focus:ring-[#5A2F59]/15 transition-all text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#6F6A67] uppercase tracking-wider mb-2">Password</label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#B0A79E]" />
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Choose a strong password"
                className="w-full pl-11 pr-4 py-3 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#5A2F59]/50 rounded-xl text-[#241C20] placeholder-[#B0A79E] focus:outline-none focus:ring-2 focus:ring-[#5A2F59]/15 transition-all text-sm"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-[#6F6A67] uppercase tracking-wider mb-2">Confirm Password</label>
            <div className="relative">
              <Lock className="absolute left-4 top-1/2 -translate-y-1/2 w-4 h-4 text-[#B0A79E]" />
              <input
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="Confirm your password"
                className="w-full pl-11 pr-4 py-3 bg-[#F7F2EC] border border-[#E8DED3] focus:border-[#5A2F59]/50 rounded-xl text-[#241C20] placeholder-[#B0A79E] focus:outline-none focus:ring-2 focus:ring-[#5A2F59]/15 transition-all text-sm"
              />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full mt-2 py-3 bg-[#5A2F59] hover:bg-[#4A2549] text-[#FFFDFC] rounded-xl text-sm font-semibold shadow-md shadow-[#5A2F59]/20 hover:shadow-[#5A2F59]/30 active:scale-[0.98] transition-all flex items-center justify-center gap-2 group disabled:opacity-60 disabled:pointer-events-none"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Registering...
              </>
            ) : (
              <>
                Get started
                <ArrowRight className="w-4 h-4 group-hover:translate-x-0.5 transition-transform" />
              </>
            )}
          </button>
        </form>

        <div className="mt-8 text-center border-t border-[#E8DED3] pt-6">
          <p className="text-sm text-[#6F6A67]">
            Already have an account?{" "}
            <Link to="/login" className="text-[#5A2F59] hover:text-[#4A2549] font-semibold transition-colors">
              Sign in
            </Link>
          </p>
        </div>
      </div>
    </div>
  );
}
