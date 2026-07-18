import { Brain, BarChart3, FileText, Wand2, Shield, Zap, Database } from "lucide-react";
import ScrollFloat from "./ScrollFloat";

const features = [
  {
    icon: <Brain size={20} />,
    title: "Natural Language Queries",
    desc: "Ask questions in plain English. Our AI maps your schema and generates optimized MySQL queries in milliseconds.",
    badge: "Core",
    color: "from-indigo-500 to-violet-500",
    glow: "shadow-indigo-500/20",
  },
  {
    icon: <Wand2 size={20} />,
    title: "AI Data Cleaning Suite",
    desc: "Industry-grade preprocessing: outlier capping, imputation, text standardization, and type conversion — all automated.",
    badge: "New",
    color: "from-violet-500 to-purple-600",
    glow: "shadow-violet-500/20",
  },
  {
    icon: <BarChart3 size={20} />,
    title: "Interactive Dashboards",
    desc: "Automatically generate bar, line, scatter, and pie charts from your query results. No config required.",
    badge: "Analytics",
    color: "from-sky-500 to-indigo-500",
    glow: "shadow-sky-500/20",
  },
  {
    icon: <FileText size={20} />,
    title: "AI-Generated Reports",
    desc: "Export polished PDF and Excel reports with natural-language summaries, tables, and embedded charts.",
    badge: "Export",
    color: "from-emerald-500 to-teal-500",
    glow: "shadow-emerald-500/20",
  },
  {
    icon: <Database size={20} />,
    title: "Smart Schema Mapping",
    desc: "Automatically detects column types, maps relationships, and prepares your dataset for intelligent querying.",
    badge: "Engine",
    color: "from-amber-500 to-orange-500",
    glow: "shadow-amber-500/20",
  },
  {
    icon: <Shield size={20} />,
    title: "Audit Trail",
    desc: "Every operation is logged — query history, cell edits, data transforms — giving you complete governance.",
    badge: "Security",
    color: "from-rose-500 to-pink-500",
    glow: "shadow-rose-500/20",
  },
];

const HOW_IT_WORKS = [
  { step: "01", title: "Upload your dataset", desc: "Drop a CSV, XLS, or XLSX file. We load it into a secure MySQL session automatically." },
  { step: "02", title: "Ask in plain English", desc: "Type your question — 'Show sales by region' or 'Find top 10 customers' — and hit enter." },
  { step: "03", title: "Get instant results", desc: "SQL is generated, executed, and visualized as charts, tables, and AI summaries in under a second." },
];

export default function Features() {
  return (
    <>
      {/* Features Section */}
      <section id="features" className="py-28 bg-[#09090B] relative overflow-hidden">
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none">
          <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-indigo-600/[0.05] rounded-full blur-[80px]" />
        </div>

        <div className="max-w-6xl mx-auto px-6">
          <ScrollFloat>
            <div className="text-center max-w-2xl mx-auto mb-16">
              <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 px-3.5 py-1.5 rounded-full text-indigo-400 text-xs font-medium mb-5">
                <Zap size={11} />
                <span>Everything you need</span>
              </div>
              <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white mb-4">
                Built for analysts,
                <span className="block gradient-text-purple">powered by AI</span>
              </h2>
              <p className="text-zinc-400 text-lg leading-relaxed">
                PromptSQL turns raw data into actionable intelligence. Upload any tabular dataset and our AI handles the rest.
              </p>
            </div>
          </ScrollFloat>

          <div className="grid md:grid-cols-2 lg:grid-cols-3 gap-4">
            {features.map((feature, index) => (
              <ScrollFloat key={index} delay={index * 80}>
                <div className="group relative bg-[#111113] border border-white/[0.06] rounded-2xl p-6 hover:border-white/[0.12] transition-all duration-300 hover:-translate-y-0.5 overflow-hidden">
                  {/* Hover glow  to chage the hover colour opacity and cards opactity change opacity-0 group-hover:opacity-[10] */}
                  <div className={`absolute inset-0 opacity-0 group-hover:opacity-[0.3] transition-opacity duration-500 bg-gradient-to-br ${feature.color} rounded-2xl`} />

                  <div className="relative z-10">
                    <div className="flex items-start justify-between mb-4">
                      <div className={`p-2.5 bg-gradient-to-br ${feature.color} rounded-xl shadow-lg ${feature.glow} text-white`}>
                        {feature.icon}
                      </div>
                      <span className="text-[10px] font-semibold text-zinc-500 bg-zinc-800 px-2.5 py-1 rounded-full border border-zinc-700">
                        {feature.badge}
                      </span>
                    </div>
                    <h3 className="text-base font-semibold text-white mb-2 group-hover:text-indigo-300 transition-colors duration-200">
                      {feature.title}
                    </h3>
                    <p className="text-sm text-zinc-400 leading-relaxed">{feature.desc}</p>
                  </div>
                </div>
              </ScrollFloat>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section id="how-it-works" className="py-28 bg-[#09090B] border-t border-white/[0.05]">
        <div className="max-w-6xl mx-auto px-6">
          <ScrollFloat>
            <div className="text-center max-w-xl mx-auto mb-16">
              <h2 className="text-4xl md:text-5xl font-bold tracking-tight text-white mb-4">
                Up and running{" "}
                <span className="gradient-text-purple">in seconds</span>
              </h2>
              <p className="text-zinc-400 text-lg">
                Three simple steps to turn raw data into insight.
              </p>
            </div>
          </ScrollFloat>

          <div className="relative">
            {/* Connecting line */}
            <div className="hidden md:block absolute top-8 left-0 right-0 h-px bg-gradient-to-r from-transparent via-indigo-500/30 to-transparent" />

            <div className="grid md:grid-cols-3 gap-8">
              {HOW_IT_WORKS.map((item, i) => (
                <ScrollFloat key={i} delay={i * 120}>
                  <div className="relative group text-center">
                    <div className="relative inline-flex w-16 h-16 bg-[#111113] border border-white/[0.08] rounded-2xl items-center justify-center mb-6 mx-auto group-hover:border-indigo-500/40 transition-all duration-300 group-hover:shadow-lg group-hover:shadow-indigo-500/10">
                      <span className="text-2xl font-black gradient-text-purple">{item.step}</span>
                      <div className="absolute -inset-px bg-gradient-to-br from-indigo-500/20 to-violet-500/0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity" />
                    </div>
                    <h3 className="text-lg font-semibold text-white mb-2">{item.title}</h3>
                    <p className="text-sm text-zinc-400 leading-relaxed">{item.desc}</p>
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
