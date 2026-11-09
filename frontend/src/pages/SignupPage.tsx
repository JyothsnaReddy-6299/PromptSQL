import { useState } from "react";
import { useNavigate } from "react-router-dom";
import Navbar from "../components/Navbar";
import Hero from "../components/Hero";
import Features from "../components/Features";
import Footer from "../components/Footer";
import AuthModal from "../components/AuthModal";

export default function SignupPage() {
  const navigate = useNavigate();
  const [isOpen, setIsOpen] = useState(true);

  return (
    <div className="relative min-h-screen bg-[#F7F2EC] overflow-hidden">
      {/* Background Page (will be blurred by AuthModal) */}
      <Navbar />
      <Hero />
      <Features />
      <Footer />

      {/* Pop View Sign Up Modal with Blurred Background */}
      <AuthModal
        isOpen={isOpen}
        initialMode="signup"
        onClose={() => {
          setIsOpen(false);
          navigate("/");
        }}
        onSuccess={() => {
          navigate("/");
        }}
      />
    </div>
  );
}
