import Navbar from "../components/Navbar";
import Hero from "../components/Hero";
import Features from "../components/Features";
import CTA from "../components/CTA";
import Footer from "../components/Footer";

export default function LandingPage() {
  return (
    <div className="relative overflow-hidden min-h-screen bg-gradient-to-b from-warmgray-50 via-white to-white">
      {/* Decorative Blob */}
      <div className="absolute top-0 left-0 w-96 h-96 bg-terracotta-100/50 rounded-full blur-3xl opacity-35" />
      <div className="absolute top-0 right-0 w-96 h-96 bg-sand-100/50 rounded-full blur-3xl opacity-35" />

      <div className="relative z-10">
        <Navbar />
        <Hero />
        <Features />
        <CTA />
        <Footer />
      </div>
    </div>
  );
}