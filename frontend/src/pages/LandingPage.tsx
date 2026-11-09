import { useState, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import Navbar from "../components/Navbar";
import Hero from "../components/Hero";
import Features from "../components/Features";
import CTA from "../components/CTA";
import Footer from "../components/Footer";
import QueryWorkspaceModal from "../components/QueryWorkspaceModal";
import AuthModal from "../components/AuthModal";

export default function LandingPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [isAuthModalOpen, setIsAuthModalOpen] = useState(false);
  const [authMode, setAuthMode] = useState<"login" | "signup">("login");
  const [authRefreshKey, setAuthRefreshKey] = useState(0);

  // Check URL query param ?auth=login or ?auth=signup
  useEffect(() => {
    const authParam = searchParams.get("auth");
    if (authParam === "login" || authParam === "signup") {
      setAuthMode(authParam);
      setIsAuthModalOpen(true);
    }
  }, [searchParams]);

  const handleOpenAuth = (mode: "login" | "signup" = "login") => {
    setAuthMode(mode);
    setIsAuthModalOpen(true);
  };

  const handleCloseAuth = () => {
    setIsAuthModalOpen(false);
    if (searchParams.has("auth")) {
      const newParams = new URLSearchParams(searchParams);
      newParams.delete("auth");
      setSearchParams(newParams, { replace: true });
    }
  };

  const handleStartQuery = () => {
    const token = localStorage.getItem("promptsql_token");
    if (!token) {
      // Instead of navigating away to a different page, open the pop view!
      handleOpenAuth("login");
      return;
    }
    // If signed in, show the datasets options modal
    setIsModalOpen(true);
  };

  const handleAuthSuccess = () => {
    setAuthRefreshKey((prev) => prev + 1);
  };

  return (
    <div className="relative min-h-screen bg-[#F7F2EC] overflow-hidden">
      <Navbar
        onStartQuery={handleStartQuery}
        onOpenAuth={handleOpenAuth}
        authRefreshKey={authRefreshKey}
      />
      <Hero onStartQuery={handleStartQuery} />
      <Features />
      <CTA onStartQuery={handleStartQuery} />
      <Footer onStartQuery={handleStartQuery} />
      
      {isModalOpen && (
        <QueryWorkspaceModal onClose={() => setIsModalOpen(false)} />
      )}

      {/* Pop View Auth Modal with Blurred Background */}
      <AuthModal
        isOpen={isAuthModalOpen}
        initialMode={authMode}
        onClose={handleCloseAuth}
        onSuccess={handleAuthSuccess}
      />
    </div>
  );
}