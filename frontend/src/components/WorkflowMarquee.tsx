import { useState, useEffect } from "react";
import { 
  Upload, 
  MessageSquare, 
  Brain, 
  Terminal, 
  BarChart3, 
  Cpu, 
  History, 
  Download,
  Wand2
} from "lucide-react";

interface WorkflowStep {
  id: string;
  icon: any;
  title: string;
  subtitle: string;
  micro: React.ReactNode;
}

export default function WorkflowMarquee() {
  const [mousePos, setMousePos] = useState({ x: 0, y: 0 });

  const handleMouseMove = (e: React.MouseEvent) => {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = ((e.clientX - rect.left) / rect.width - 0.5) * 20;
    const y = ((e.clientY - rect.top) / rect.height - 0.5) * 20;
    setMousePos({ x, y });
  };

  const handleMouseLeave = () => {
    setMousePos({ x: 0, y: 0 });
  };

  // AI Response state loop for complete check
  const [aiStatus, setAiStatus] = useState("Generating...");
  useEffect(() => {
    const interval = setInterval(() => {
      setAiStatus((prev) => (prev === "Generating..." ? "Complete ✓" : "Generating..."));
    }, 2500);
    return () => clearInterval(interval);
  }, []);

  // SQL code typer loop state
  const [sqlTyped, setSqlTyped] = useState("S");
  useEffect(() => {
    const code = "SELECT * FROM `sales` WHERE `region` = 'West'";
    let i = 1;
    const interval = setInterval(() => {
      setSqlTyped(code.slice(0, i));
      i++;
      if (i > code.length + 5) {
        i = 1;
      }
    }, 150);
    return () => clearInterval(interval);
  }, []);

  const steps: WorkflowStep[] = [
    {
      id: "upload",
      icon: <Upload size={18} className="text-[#5A2F59]" />,
      title: "Upload Dataset",
      subtitle: "Ingest CSV, XLS, XLSX",
      micro: (
        <div className="w-full bg-[#E8DED3] rounded-full h-1 mt-2.5 overflow-hidden">
          <div className="bg-[#5A2F59] h-full rounded-full animate-fill-progress" />
        </div>
      )
    },
    {
      id: "query",
      icon: <MessageSquare size={18} className="text-[#5A2F59]" />,
      title: "Natural Query",
      subtitle: "Ask questions in plain English",
      micro: (
        <div className="flex items-center gap-0.5 mt-2 bg-[#34182F] px-2 py-1 rounded font-mono text-[9px] text-[#BDA37A] border border-[#5A2F59]/30">
          <span>&gt; Find average sales</span>
          <span className="w-1 h-3 bg-[#BDA37A] animate-blink" />
        </div>
      )
    },
    {
      id: "schema",
      icon: <Brain size={18} className="text-[#5A2F59]" />,
      title: "Analyze Schema",
      subtitle: "Understand columns & data types",
      micro: (
        <div className="flex gap-1.5 justify-center mt-2.5">
          <span className="w-1.5 h-1.5 rounded-full bg-[#5A2F59] animate-ping" />
          <span className="w-1.5 h-1.5 rounded-full bg-[#5A2F59]/70 animate-pulse" />
          <span className="w-1.5 h-1.5 rounded-full bg-[#BDA37A] animate-bounce" />
        </div>
      )
    },
    {
      id: "sql",
      icon: <Terminal size={18} className="text-[#5A2F59]" />,
      title: "Generate SQL",
      subtitle: "Compile optimized MySQL queries",
      micro: (
        <div className="mt-2 bg-[#34182F] text-[#BDA37A] font-mono text-[8.5px] p-1.5 rounded border border-[#5A2F59]/30 overflow-hidden truncate h-7 flex items-center leading-none">
          <code>{sqlTyped}</code>
        </div>
      )
    },
    {
      id: "extract",
      icon: <BarChart3 size={18} className="text-[#5A2F59]" />,
      title: "Extract Data",
      subtitle: "Execute query inside transaction",
      micro: (
        <div className="flex justify-center items-end gap-1 mt-2.5 h-4">
          <div className="w-1 bg-[#5A2F59] rounded-t animate-height-grow" style={{ animationDelay: "0.1s" }} />
          <div className="w-1 bg-[#BDA37A] rounded-t animate-height-grow" style={{ animationDelay: "0.3s" }} />
          <div className="w-1 bg-[#5A2F59]/70 rounded-t animate-height-grow" style={{ animationDelay: "0.5s" }} />
          <div className="w-1 bg-[#BDA37A]/70 rounded-t animate-height-grow" style={{ animationDelay: "0.2s" }} />
        </div>
      )
    },
    {
      id: "ai",
      icon: <Cpu size={18} className="text-[#5A2F59]" />,
      title: "AI Response",
      subtitle: "Summarize trends & behaviors",
      micro: (
        <div className="mt-2 text-center">
          <span className={`px-2 py-0.5 text-[8.5px] font-bold rounded-full border transition-all duration-300 ${
            aiStatus === "Generating..."
              ? "bg-[#BDA37A]/15 border-[#BDA37A]/30 text-[#BDA37A] animate-pulse"
              : "bg-[#3E8E5B]/10 border-[#3E8E5B]/25 text-[#3E8E5B]"
          }`}>
            {aiStatus}
          </span>
        </div>
      )
    },
    {
      id: "history",
      icon: <History size={18} className="text-[#5A2F59]" />,
      title: "Save History",
      subtitle: "Log operations chronologically",
      micro: (
        <div className="flex gap-1 justify-center mt-3 text-[8px] font-bold text-[#5A2F59]">
          <span className="opacity-40 animate-pulse">●</span>
          <span className="opacity-70 animate-pulse" style={{ animationDelay: "0.3s" }}>●</span>
          <span className="opacity-100 animate-pulse" style={{ animationDelay: "0.6s" }}>●</span>
        </div>
      )
    },
    {
      id: "data cleaner",
      icon: <Wand2 size={18} className="text-[#5A2F59]" />,
      title: "Smart Data Cleaner",
      subtitle: "Clean up dataset anomalies",
      micro: (
        <div className="flex items-center gap-1 justify-center mt-2.5 bg-[#5A2F59]/5 px-2 py-0.5 rounded border border-[#5A2F59]/10 text-[#5A2F59] font-mono text-[8px] font-bold animate-pulse">
          <span>[NULL]</span>
          <span className="text-[7px] text-[#BDA37A]">→</span>
          <span>REPAIRED</span>
        </div>
      )
    },
    {
      id: "export",
      icon: <Download size={18} className="text-[#5A2F59]" />,
      title: "Export Results",
      subtitle: "Download reports in PDF & XLS",
      micro: (
        <div className="flex justify-center mt-2 font-bold text-[#5A2F59] animate-arrow-bounce">
          <Download size={12} />
        </div>
      )
    }
  ];

  // Repeat steps to create continuous marquee trail
  const marqueeSteps = [...steps, ...steps];

  return (
    <div 
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      className="relative w-full border-y border-[#E8DED3] bg-[#F7F2EC] overflow-hidden min-h-[170px] flex items-center py-6"
    >
      {/* Subtle Grid Pattern Background */}
      <div className="absolute inset-0 bg-[linear-gradient(to_right,#ffffff02_1px,transparent_1px),linear-gradient(to_bottom,#ffffff02_1px,transparent_1px)] bg-[size:16px_20px] pointer-events-none" />

      {/* Blurred glowing blobs with mouse parallax */}
      <div 
        style={{
          transform: `translate3d(${mousePos.x * -0.6}px, ${mousePos.y * -0.6}px, 0)`,
          transition: "transform 0.2s ease-out"
        }}
        className="absolute top-10 left-1/4 w-32 h-32 bg-[#5A2F59]/8 rounded-full blur-2xl pointer-events-none" 
      />
      <div 
        style={{
          transform: `translate3d(${mousePos.x * 0.4}px, ${mousePos.y * 0.4}px, 0)`,
          transition: "transform 0.2s ease-out"
        }}
        className="absolute bottom-6 right-1/4 w-40 h-40 bg-[#BDA37A]/8 rounded-full blur-3xl pointer-events-none" 
      />

      {/* Custom floating particle dots */}
      <div className="absolute top-4 right-12 w-2 h-2 rounded-full bg-[#5A2F59]/20 animate-bounce pointer-events-none" />
      <div className="absolute bottom-8 left-16 w-1.5 h-1.5 rounded-full bg-[#BDA37A]/25 animate-ping pointer-events-none" />

      {/* Infinite loop marquee track */}
      <div className="w-full overflow-hidden py-4 z-10">
        <div className="animate-marquee gap-5 flex items-center">
          {marqueeSteps.map((step, idx) => (
            <div
              key={idx}
              className="w-56 shrink-0 bg-[#FFFDFC] border border-[#E8DED3] hover:border-[#5A2F59]/30 rounded-2xl p-4 shadow-sm hover:shadow-md transition-all duration-300 hover:scale-105 hover:-rotate-1 select-none text-left"
              style={{ 
                boxShadow: "0 4px 20px -4px rgba(90, 47, 89, 0.08)"
              }}
            >
              <div className="flex items-center gap-3">
                <div className="bg-[#5A2F59]/10 border border-[#5A2F59]/20 p-2 rounded-xl text-[#5A2F59] flex items-center justify-center shrink-0">
                  {step.icon}
                </div>
                <div className="overflow-hidden">
                  <h4 className="text-xs font-bold text-[#241C20] truncate">
                    {step.title}
                  </h4>
                  <p className="text-[9px] text-[#6F6A67] truncate mt-0.5 leading-none">
                    {step.subtitle}
                  </p>
                </div>
              </div>
              
              {/* Micro-interaction element */}
              <div className="h-10 flex flex-col justify-end">
                {step.micro}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
