import Navbar from "../components/Navbar";
import Hero from "../components/Hero";
import Features from "../components/Features";
import CTA from "../components/CTA";
import Footer from "../components/Footer";

export default function LandingPage() {

    return (

        <div className="relative overflow-hidden min-h-screen bg-gradient-to-b from-blue-50 via-white to-white">


            <div className="absolute top-0 left-0 w-96 h-96 bg-blue-200 rounded-full blur-3xl opacity-40" />

            <div className="absolute top-0 right-0 w-96 h-96 bg-cyan-200 rounded-full blur-3xl opacity-40" />



            <div className="relative z-10">

                <Navbar />     {/* this order of the different components stack them vertically in the page */}

                <Hero />

                <Features />

                <CTA />
                <Footer />

            </div>

        </div>

    );
}