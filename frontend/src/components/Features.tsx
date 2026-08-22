import { Brain, BarChart3, FileText, Wand2, Shield, Zap, Database } from "lucide-react";
import ScrollFloat from "./ScrollFloat";

const features = [
  {
    icon: <Brain size={20} />,
    title: "Natural Language Queries",
    desc: "Ask questions in plain English. Our AI maps your schema and generates optimized MySQL queries in seconds.",
    badge: "Core",
    iconBg: "bg-[#5A2F59]",
    iconText: "text-[#BDA37A]",
  },
  {
    icon: <Wand2 size={20} />,
    title: "AI Data Cleaning Suite",
    desc: "Industry-grade preprocessing: imputation, text standardization, and type conversion — all automated.",
    badge: "New",
    iconBg: "bg-[#5A2F59]/80",
    iconText: "text-[#BDA37A]",
  },
  {
    icon: <BarChart3 size={20} />,
    title: "Editable Preview Table",
    desc: "Edit your table by a double click on any data which you want to update or add.",
    badge: "Edit",
    iconBg: "bg-[#BDA37A]/80",
    iconText: "text-[#34182F]",
  },
  {
    icon: <FileText size={20} />,
    title: "AI-Generated Reports",
    desc: "Export polished PDF and Excel reports with natural-language summaries and tables.",
    badge: "Export",
    iconBg: "bg-[#3E8E5B]",
    iconText: "text-[#FFFDFC]",
  },
  {
    icon: <Database size={20} />,
    title: "Smart Schema Mapping",
    desc: "Automatically detects column types, maps relationships, and prepares your dataset for intelligent querying.",
    badge: "Engine",
    iconBg: "bg-[#BDA37A]",
    iconText: "text-[#34182F]",
  },
  {
    icon: <Shield size={20} />,
    title: "Audit Trail",
    desc: "Every operation is logged — query history, cell edits, data transforms — giving you complete governance.",
    badge: "Security",
    iconBg: "bg-[#D95D39]",
    iconText: "text-[#FFFDFC]",
  },
];

const HOW_IT_WORKS = [
  { step: "01", title: "Upload your dataset", desc: "Drop a CSV, XLS, or XLSX file. We load it into a secure MySQL session automatically." },
  { step: "02", title: "Ask in plain English", desc: "Type your question — 'Show sales by region' or 'Find top 10 customers' — and hit enter." },
  { step: "03", title: "Get instant results", desc: "SQL is generated, executed, and visualized as tables and AI summaries in under a second." },
];

export default function Features() {
  return (
    <>
      {/* Features Section */}
      <section id="features" className="py-28 bg-[#F7F2EC] relative overflow-hidden">
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-[#5A2F59]/4 rounded-full blur-[80px]" />
        </div>

        <div className="max-w-6xl mx-auto px-6">
          <ScrollFloat>
            <div className="text-center max-w-2xl mx-auto mb-16">
              <div className="inline-flex items-center gap-2 bg-[#5A2F59]/8 border border-[#5A2F59]/20 px-3.5 py-1.5 rounded-full text-[#5A2F59] text-xs font-medium mb-5">
                <Zap size={11} />
                <span>Everything you need</span>
              </div>
              <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-[#241C20] mb-4">
                Built for analysts,
                <span className="block gradient-text-purple">powered by AI</span>
              </h2>
              <p className="text-[#6F6A67] text-lg leading-relaxed">
                PromptSQL turns raw data into actionable intelligence. Upload any tabular dataset and our AI handles the rest.
              </p>
            </div>
          </ScrollFloat>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {features.map((feature, index) => (
              <ScrollFloat key={index} delay={index * 80}>
                <div className="group relative bg-[#FFFDFC] border border-[#E8DED3] rounded-2xl p-6 hover:border-[#5A2F59]/25 hover:shadow-lg hover:shadow-[#5A2F59]/5 transition-all duration-300 hover:-translate-y-0.5 overflow-hidden">
                  {/* Hover tint */}
                  <div className="absolute inset-0 opacity-0 group-hover:opacity-100 transition-opacity duration-500 bg-[#5A2F59]/[0.015] rounded-2xl" />

                  <div className="relative z-10">
                    <div className="flex items-start justify-between mb-4">
                      <div className={`p-2.5 ${feature.iconBg} rounded-xl shadow-sm ${feature.iconText}`}>
                        {feature.icon}
                      </div>
                      <span className="text-[10px] font-semibold text-[#6F6A67] bg-[#F7F2EC] px-2.5 py-1 rounded-full border border-[#E8DED3]">
                        {feature.badge}
                      </span>
                    </div>
                    <h3 className="text-base font-semibold text-[#241C20] mb-2 group-hover:text-[#5A2F59] transition-colors duration-200">
                      {feature.title}
                    </h3>
                    <p className="text-sm text-[#6F6A67] leading-relaxed">{feature.desc}</p>
                  </div>
                </div>
              </ScrollFloat>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-28 bg-[#FFFDFC] border-t border-[#E8DED3]">
        <div className="max-w-6xl mx-auto px-6">
          <ScrollFloat>
            <div className="text-center max-w-xl mx-auto mb-16">
              <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-[#241C20] mb-4">
                Up and running{" "}
                <span className="gradient-text-purple">in seconds</span>
              </h2>
              <p className="text-[#6F6A67] text-lg">
                Three simple steps to turn raw data into insight.
              </p>
            </div>
          </ScrollFloat>

          <div className="relative">
            {/* Connecting line */}
            <div className="hidden md:block absolute top-8 left-0 right-0 h-px bg-gradient-to-r from-transparent via-[#5A2F59]/20 to-transparent" />

            <div className="grid md:grid-cols-3 gap-8">
              {HOW_IT_WORKS.map((item, i) => (
                <ScrollFloat key={i} delay={i * 120}>
                  <div className="relative group text-center">
                    <div className="relative inline-flex w-16 h-16 bg-[#FFFDFC] border border-[#E8DED3] rounded-2xl items-center justify-center mb-6 mx-auto group-hover:border-[#5A2F59]/30 transition-all duration-300 group-hover:shadow-lg group-hover:shadow-[#5A2F59]/8">
                      <span className="text-2xl font-black gradient-text-purple">{item.step}</span>
                      <div className="absolute -inset-px bg-[#5A2F59]/5 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <h3 className="text-lg font-semibold text-[#241C20] mb-2">{item.title}</h3>
                    <p className="text-sm text-[#6F6A67] leading-relaxed">{item.desc}</p>
                  </div>
                </ScrollFloat>
              ))}
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
