import { Brain } from "lucide-react";
import { useNavigate } from "react-router-dom";

const LINKS = {
  Product: ["Features", "Analytics", "Data Cleaning", "Reports"],
  Resources: ["Documentation", "API Reference", "Changelog", "Status"],
  Company: ["About", "Blog", "Careers", "Contact"],
};

export default function Footer() {
  const navigate = useNavigate();
  const currentYear = new Date().getFullYear();

  return (
    <footer className="bg-[#34182F] border-t border-[#5A2F59]/30">
      <div className="max-w-6xl mx-auto px-6 py-16">
        <div className="grid md:grid-cols-5 gap-12 mb-12">
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
            <div className="flex items-center gap-3">
              <a
                href="#"
                className="w-8 h-8 bg-[#5A2F59]/40 hover:bg-[#5A2F59]/70 border border-[#BDA37A]/15 hover:border-[#BDA37A]/30 rounded-lg flex items-center justify-center text-[#E8DED3]/50 hover:text-[#BDA37A] transition-all cursor-pointer"
              >
                <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24"><path d="M12 .297c-6.63 0-12 5.373-12 12 0 5.303 3.438 9.8 8.205 11.385.6.113.82-.258.82-.577 0-.285-.01-1.04-.015-2.04-3.338.724-4.042-1.61-4.042-1.61C4.422 18.07 3.633 17.7 3.633 17.7c-1.087-.744.084-.729.084-.729 1.205.084 1.838 1.236 1.838 1.236 1.07 1.835 2.809 1.305 3.495.998.108-.776.417-1.305.76-1.605-2.665-.3-5.466-1.332-5.466-5.93 0-1.31.465-2.38 1.235-3.22-.135-.303-.54-1.523.105-3.176 0 0 1.005-.322 3.3 1.23.96-.267 1.98-.399 3-.405 1.02.006 2.04.138 3 .405 2.28-1.552 3.285-1.23 3.285-1.23.645 1.653.24 2.873.12 3.176.765.84 1.23 1.91 1.23 3.22 0 4.61-2.805 5.625-5.475 5.92.42.36.81 1.096.81 2.22 0 1.606-.015 2.896-.015 3.286 0 .315.21.69.825.57C20.565 22.092 24 17.592 24 12.297c0-6.627-5.373-12-12-12"/></svg>
              </a>
              <a
                href="#"
                className="w-8 h-8 bg-[#5A2F59]/40 hover:bg-[#5A2F59]/70 border border-[#BDA37A]/15 hover:border-[#BDA37A]/30 rounded-lg flex items-center justify-center text-[#E8DED3]/50 hover:text-[#BDA37A] transition-all cursor-pointer"
              >
                <svg className="w-4 h-4 fill-current" viewBox="0 0 24 24"><path d="M23.953 4.57a10 10 0 01-2.825.775 4.958 4.958 0 002.163-2.723c-.951.555-2.005.959-3.127 1.184a4.92 4.92 0 00-8.384 4.482C7.69 8.095 4.067 6.13 1.64 3.162a4.822 4.822 0 00-.666 2.475c0 1.71.87 3.213 2.188 4.096a4.904 4.904 0 01-2.228-.616v.06a4.923 4.923 0 003.946 4.827 4.996 4.996 0 01-2.212.085 4.936 4.936 0 004.604 3.417 9.867 9.867 0 01-6.102 2.105c-.39 0-.779-.023-1.17-.067a13.995 13.995 0 007.557 2.209c9.053 0 13.998-7.496 13.998-13.985 0-.21 0-.42-.015-.63A9.935 9.935 0 0024 4.59z"/></svg>
              </a>
            </div>
          </div>

          {/* Link columns */}
          {Object.entries(LINKS).map(([section, items]) => (
            <div key={section}>
              <h4 className="text-xs font-semibold text-[#BDA37A] uppercase tracking-wider mb-4">
                {section}
              </h4>
              <ul className="space-y-3">
                {items.map((item) => (
                  <li key={item}>
                    <a className="text-sm text-[#E8DED3]/50 hover:text-[#FFFDFC] transition-colors cursor-pointer">
                      {item}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          ))}
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
