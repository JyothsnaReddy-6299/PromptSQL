import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";
import Hero from "../components/Hero";
import Features from "../components/Features";
import CTA from "../components/CTA";
import Footer from "../components/Footer";
import QueryWorkspaceModal from "../components/QueryWorkspaceModal";

export default function LandingPage() {
  const navigate = useNavigate();
  const [isModalOpen, setIsModalOpen] = useState(false);

  const handleStartQuery = () => {
    const token = localStorage.getItem("promptsql_token");
    if (!token) {
      // If not signed in, redirect to login page
      navigate("/login");
      return;
    }
    // If signed in, show the datasets options modal
    setIsModalOpen(true);
  };

  return (
    <div className="relative min-h-screen bg-[#F7F2EC] overflow-hidden">
      <Navbar onStartQuery={handleStartQuery} />
      <Hero onStartQuery={handleStartQuery} />
      <Features />
      <CTA onStartQuery={handleStartQuery} />
      <Footer onStartQuery={handleStartQuery} />
      
      {isModalOpen && (
        <QueryWorkspaceModal onClose={() => setIsModalOpen(false)} />
      )}
    </div>
  );
}