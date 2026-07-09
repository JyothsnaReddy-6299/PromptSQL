import { Brain, BarChart3, Sparkles, FileText } from "lucide-react";

const cards = [
  {
    title: "Natural Language Queries",
    icon: <Brain size={20} />,
    desc: "Ask questions about your data in plain English and get instant SQL and answers.",
    color: "from-terracotta-500 to-terracotta-600",
    bg: "bg-terracotta-50"
  },
  {
    title: "Automated Insights",
    icon: <Sparkles size={20} />,
    desc: "Automatically detect key columns, trends, and outliers from any uploaded dataset.",
    color: "from-sand-400 to-terracotta-500",
    bg: "bg-sand-50"
  },
  {
    title: "Interactive Dashboards",
    icon: <BarChart3 size={20} />,
    desc: "Visualize your queries and aggregate results using dynamic charts generated on the fly.",
    color: "from-terracotta-600 to-sand-400",
    bg: "bg-terracotta-50"
  },
  {
    title: "AI Reports",
    icon: <FileText size={20} />,
    desc: "Generate detailed, natural-language interpretations and tabular outputs of your data.",
    color: "from-terracotta-500 to-sand-300",
    bg: "bg-sand-50"
  }
];

export default function Features() {
  return (
    <section id="features" className="py-20 bg-gradient-to-b from-white via-warmgray-50 to-warmgray-100/50">
      <div className="max-w-5xl mx-auto px-6">
        <div className="text-center max-w-2xl mx-auto mb-14">
          <h2 className="text-3xl font-extrabold tracking-tight text-warmgray-900 sm:text-4xl">
            Analyze datasets in seconds,
            <span className="block mt-1 bg-gradient-to-r from-terracotta-500 to-terracotta-600 bg-clip-text text-transparent">
              without writing SQL
            </span>
          </h2>
          <p className="mt-4 text-sm text-warmgray-500 font-medium">
            PromptSQL is dataset-agnostic. Upload any tabular dataset and our AI will immediately map its schema, clean columns, and prepare it for analysis.
          </p>
        </div>

        <div className="grid md:grid-cols-2 gap-6 lg:gap-8">
          {cards.map((card, index) => (
            <div 
              key={index}
              className="group relative bg-white border border-warmgray-100 rounded-2xl p-6 shadow-sm hover:shadow-lg hover:-translate-y-0.5 transition-all duration-300 overflow-hidden"
            >
              <div className="absolute top-0 left-0 w-1.5 h-full bg-gradient-to-b from-terracotta-500 to-sand-300 opacity-0 group-hover:opacity-100 transition-opacity duration-300" />
              
              <div className="flex gap-4 items-start">
                <div className={`p-3 rounded-xl bg-gradient-to-br ${card.color} text-white shadow-md shadow-terracotta-500/10 shrink-0`}>
                  {card.icon}
                </div>
                <div>
                  <h3 className="text-base font-bold text-warmgray-900 group-hover:text-terracotta-600 transition-colors">
                    {card.title}
                  </h3>
                  <p className="mt-2 text-xs text-warmgray-500 leading-relaxed font-medium">
                    {card.desc}
                  </p>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
