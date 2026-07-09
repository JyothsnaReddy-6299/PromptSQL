import { Sparkles, ArrowRight, Play, Database } from "lucide-react";
import { useNavigate } from "react-router-dom";

export default function Hero() {
  const navigate = useNavigate();

  const handleUploadClick = () => {
    navigate("/upload");
  };

  return (
    <section className="relative pt-28 pb-14 md:pt-32 md:pb-16 bg-warmgray-50 overflow-hidden">
      {/* Decorative Warm Blur Blobs */}
      <div className="absolute top-1/4 left-1/10 w-96 h-96 bg-terracotta-300 rounded-full filter blur-3xl opacity-15 animate-pulse" />
      <div className="absolute top-1/3 right-1/10 w-96 h-96 bg-sand-200 rounded-full filter blur-3xl opacity-20 animate-pulse duration-5000" />

      <div className="relative z-10 max-w-5xl mx-auto px-6 text-center">
        {/* Badge */}
        <div className="inline-flex items-center gap-2 bg-terracotta-50 border border-terracotta-100 px-4 py-1.5 rounded-full text-terracotta-700 font-semibold text-[10px] animate-fade-in hover:scale-103 transition-transform duration-300">
          <Sparkles size={12} className="text-terracotta-500 animate-spin-slow" />
          <span>AI-Powered Text-to-SQL Analytics Engine</span>
        </div>

        {/* Heading - Reduced Size */}
        <h1 className="mt-5 text-4xl md:text-5xl lg:text-6xl font-black text-warmgray-900 tracking-tight leading-none">
          Talk to Your Data
          <span className="block mt-2.5 bg-gradient-to-r from-terracotta-600 via-terracotta-500 to-sand-400 bg-clip-text text-transparent">
            Like a Human.
          </span>
        </h1>

        {/* Subtitle - Reduced Size */}
        <p className="mt-5 text-sm md:text-base lg:text-lg text-warmgray-500 max-w-2xl mx-auto leading-relaxed font-medium">
          Upload any CSV or Excel spreadsheet and immediately interrogate it using natural language. No complex database query writing, no custom schema mapping—just instant insights.
        </p>

        {/* CTAs - Spacing & Padding Reduced */}
        <div className="mt-8 flex flex-col sm:flex-row gap-4 justify-center items-center">
          <button
            onClick={handleUploadClick}
            className="w-full sm:w-auto bg-gradient-to-r from-terracotta-500 via-terracotta-600 to-sand-400 px-8 py-3.5 rounded-xl text-white font-bold text-sm shadow-md shadow-terracotta-500/10 hover:scale-105 active:scale-98 transition duration-300 flex items-center justify-center gap-2.5 cursor-pointer"
          >
            <span>Start Analyzing Free</span>
            <ArrowRight size={16} className="group-hover:translate-x-1 transition-transform" />
          </button>

          <a
            href="#features"
            className="w-full sm:w-auto bg-white border border-warmgray-100 text-warmgray-850 px-6 py-3.5 rounded-xl font-bold text-sm hover:bg-warmgray-100 hover:text-warmgray-900 active:scale-98 transition flex items-center justify-center gap-2 cursor-pointer"
          >
            <Play size={14} className="fill-warmgray-500 text-warmgray-500" />
            <span>Explore Features</span>
          </a>
        </div>

        {/* Dashboard Mockup Preview - Compact Height and Fonts */}
        <div className="mt-12 relative rounded-2xl border border-warmgray-100 bg-white/70 p-3 shadow-xl max-w-3xl mx-auto backdrop-blur-sm group hover:border-terracotta-300 transition-colors duration-500">
          <div className="flex gap-1.5 mb-2 px-1">
            <div className="w-2.5 h-2.5 rounded-full bg-terracotta-300/80" />
            <div className="w-2.5 h-2.5 rounded-full bg-sand-200" />
            <div className="w-2.5 h-2.5 rounded-full bg-warmgray-200" />
          </div>
          <div className="bg-warmgray-950 rounded-xl p-4.5 text-left font-mono text-xs text-warmgray-300 shadow-inner overflow-hidden relative">
            {/* Background glowing shape inside mockup */}
            <div className="absolute bottom-0 right-0 w-60 h-60 bg-terracotta-500 rounded-full filter blur-3xl opacity-10" />

            <div className="flex justify-between border-b border-warmgray-900 pb-3 mb-3">
              <span className="text-warmgray-500 flex items-center gap-1.5">
                <Database size={12} /> employee_sales_data.csv
              </span>
              <span className="text-terracotta-400 font-bold">● Connected</span>
            </div>
            
            <p className="text-warmgray-500">// User Question</p>
            <p className="text-white text-sm font-semibold mb-3">
              &gt; "Show average salary and total sales grouped by department ordered by sales descending"
            </p>
            
            <p className="text-warmgray-500">// Generated SQL Query</p>
            <p className="text-terracotta-300 mb-3 leading-relaxed">
              <span className="text-sand-300">SELECT</span> `Department`, <span className="text-sand-300">AVG</span>(`Salary`) <span className="text-sand-300">AS</span> `Average Salary`, <span className="text-sand-300">SUM</span>(`Sales`) <span className="text-sand-300">AS</span> `Total Sales`<br />
              <span className="text-sand-300">FROM</span> `employee_sales_data`<br />
              <span className="text-sand-300">GROUP BY</span> `Department`<br />
              <span className="text-sand-300">ORDER BY</span> `Total Sales` <span className="text-sand-300">DESC</span>;
            </p>
            
            <p className="text-warmgray-500">// AI Response Summary</p>
            <p className="text-cream-200 leading-relaxed">
              "The Sales department generated the highest total revenue ($1.4M) with an average salary of $78,500. Marketing follows with $980K in sales, while HR has the lowest sales figures ($340K) but highest salary average ($82,000)."
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}