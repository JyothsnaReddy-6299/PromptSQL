import { Brain } from "lucide-react";
import { useNavigate } from "react-router-dom";

interface FooterProps {
  onStartQuery?: () => void;
}

export default function Footer({ onStartQuery }: FooterProps) {
  const navigate = useNavigate();
  const currentYear = new Date().getFullYear();

  const handleProductLinkClick = (e: React.MouseEvent, item: string) => {
    e.preventDefault();
    if (item === "Features") {
      const element = document.getElementById("features");
      if (element) {
        element.scrollIntoView({ behavior: "smooth" });
      } else {
        navigate("/#features");
      }
    } else {
      if (onStartQuery) {
        onStartQuery();
      } else {
        navigate("/upload");
      }
    }
  };

  return (
    <footer className="bg-[#34182F] border-t border-[#5A2F59]/30">
      <div className="max-w-6xl mx-auto px-6 py-16">
        <div className="grid md:grid-cols-3 gap-12 mb-12">
          {/* Brand column */}
          <div className="md:col-span-2">
            <div
              onClick={() => navigate("/")}
              className="flex items-center gap-2.5 cursor-pointer group mb-4"
            >
              <div className="w-8 h-8 bg-[#5A2F59] border border-[#BDA37A]/20 rounded-lg flex items-center justify-center">
                <Brain size={16} className="text-[#BDA37A]" />
              </div>
              <span className="text-base font-bold text-[#FFFDFC] group-hover:text-[#BDA37A] transition-colors">
                PromptSQL
              </span>
            </div>
            <p className="text-sm text-[#E8DED3]/50 leading-relaxed max-w-xs mb-6">
              Natural language meets SQL intelligence. Query any dataset with plain English and get instant AI-powered insights.
            </p>
          </div>

          {/* Product links column */}
          <div>
            <h4 className="text-xs font-semibold text-[#BDA37A] uppercase tracking-wider mb-4">
              Product
            </h4>
            <ul className="space-y-3">
              {["Features", "Analytics", "Data Cleaning", "Reports"].map((item) => (
                <li key={item}>
                  <a
                    href="#"
                    onClick={(e) => handleProductLinkClick(e, item)}
                    className="text-sm text-[#E8DED3]/50 hover:text-[#FFFDFC] transition-colors cursor-pointer"
                  >
                    {item}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </div>

        {/* Bottom bar */}
        <div className="border-t border-[#5A2F59]/30 pt-8 flex flex-col md:flex-row items-center justify-between gap-4">
          <p className="text-xs text-[#E8DED3]/35">
            © {currentYear} PromptSQL. All rights reserved.
          </p>
          <div className="flex items-center gap-6">
            <a className="text-xs text-[#E8DED3]/35 hover:text-[#FFFDFC] transition-colors cursor-pointer">
              Privacy Policy
            </a>
            <a className="text-xs text-[#E8DED3]/35 hover:text-[#FFFDFC] transition-colors cursor-pointer">
              Terms of Service
            </a>
          </div>
        </div>
      </div>
    </footer>
  );
}
