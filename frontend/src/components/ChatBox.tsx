import { useState, useRef, useEffect } from "react";
import { 
  Send, 
  Brain, 
  Copy, 
  Check, 
  Database, 
  Download, 
  Table, 
  BarChart3, 
  ChevronLeft,
  ChevronRight,
  Search,
  Info,
  History,
  Trash2,
  FolderHeart,
  Loader2,
  AlertTriangle,
  Play
} from "lucide-react";
import axios from "axios";
import { 
  getHistory, 
  deleteHistoryItem, 
  clearHistory, 
  createReport,
  downloadActivePDF,
  downloadActiveExcel,
  downloadActiveCSV,
  askModification,
  executeModification
} from "../services/api";

interface Message {
  sender: "user" | "ai";
  text: string;
  question?: string; // Cache user question for export options
  sql?: string;
  records?: Record<string, any>[];
  error?: string;
  activeTab?: "table" | "chart";
  chartType?: "bar" | "line";
  reportSaved?: boolean;

  // Modification confirmation workflow properties
  intent?: string;
  warning?: string;
  requires_confirmation?: boolean;
  table_name?: string;
  is_executing?: boolean;
  rows_affected?: number;
  execution_time_ms?: number;
  canceled?: boolean;
}

export default function ChatBox() {
  const [question, setQuestion] = useState("");
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<Message[]>([
    {
      sender: "ai",
      text: "Hello! I am your AI Analytics Assistant. Ask me anything about your uploaded dataset in plain English. I'll translate your question into optimized SQL, fetch the results, and explain the trends for you!"
    }
  ]);
  const [copiedSql, setCopiedSql] = useState<string | null>(null);

  // History states
  const [showHistory, setShowHistory] = useState(false);
  const [historyList, setHistoryList] = useState<any[]>([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  // Saved reports inline states (for message index)
  const [saveReportIdx, setSaveReportIdx] = useState<number | null>(null);
  const [reportTitle, setReportTitle] = useState("");
  const [savingReport, setSavingReport] = useState(false);

  const messagesEndRef = useRef<HTMLDivElement>(null);

  const dataset = JSON.parse(sessionStorage.getItem("dataset") || "{}");
  const activeTableName = dataset?.filename || "Active Dataset";

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, loading]);

  useEffect(() => {
    if (showHistory) {
      loadHistoryLogs();
    }
  }, [showHistory]);

  const loadHistoryLogs = async () => {
    try {
      setLoadingHistory(true);
      const data = await getHistory();
      setHistoryList(data);
    } catch (e) {
      console.error("History load error:", e);
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleCopy = (sql: string) => {
    navigator.clipboard.writeText(sql);
    setCopiedSql(sql);
    setTimeout(() => setCopiedSql(null), 2000);
  };

  const askAI = async () => {
    if (!question.trim()) return;

    const currentQuestion = question;
    setQuestion("");
    setLoading(true);

    // Append user question
    setMessages((prev) => [
      ...prev,
      { sender: "user", text: currentQuestion }
    ]);

    try {
      // 1. Intercept user question by calling intent detector and preview generator
      const modCheck = await askModification(currentQuestion);

      if (modCheck.success && modCheck.requires_confirmation) {
        // This is a database modification (DML or DDL)
        setMessages((prev) => [
          ...prev,
          {
            sender: "ai",
            text: modCheck.impact_explanation,
            question: currentQuestion,
            sql: modCheck.sql,
            intent: modCheck.intent,
            warning: modCheck.warning,
            requires_confirmation: true,
            table_name: modCheck.table_name,
            records: []
          }
        ]);
        setLoading(false);
        return;
      }

      // 2. If it is standard SELECT, proceed through the read-only ask router
      const response = await axios.post("/ask", {
        question: currentQuestion
      });

      const data = response.data;

      if (!data.success) {
        setMessages((prev) => [
          ...prev,
          {
            sender: "ai",
            text: "I couldn't complete that query. Here's what went wrong:",
            error: data.error || "Execution failed."
          }
        ]);
        return;
      }

      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: data.summary || "Here are the retrieved records.",
          question: currentQuestion,
          sql: data.generated_sql || "",
          records: data.result || [],
          activeTab: "table",
          chartType: "bar"
        }
      ]);

      if (showHistory) {
        loadHistoryLogs();
      }

    } catch (err: any) {
      const errMsg = err.message || "Server Error";
      setMessages((prev) => [
        ...prev,
        {
          sender: "ai",
          text: "I failed to process that request.",
          error: errMsg
        }
      ]);
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmModification = async (idx: number, msg: Message) => {
    if (!msg.sql || !msg.intent || !msg.table_name) return;

    try {
      // Set executing loading state
      const updating = [...messages];
      updating[idx].is_executing = true;
      setMessages(updating);

      // Execute transactionally
      const result = await executeModification(msg.sql, msg.intent, msg.table_name);

      const finalized = [...messages];
      finalized[idx].is_executing = false;
      finalized[idx].requires_confirmation = false;

      if (result.success) {
        finalized[idx].text = result.message; // LLM generated confirmation e.g. "18 records updated."
        finalized[idx].rows_affected = result.rows_affected;
        finalized[idx].execution_time_ms = result.execution_time_ms;
        
        // Dispatch window event so explorer table fetches latest mysql table rows immediately!
        window.dispatchEvent(new Event("dataset-modified"));
      } else {
        finalized[idx].text = "Database execution failed. The transaction was automatically rolled back.";
        finalized[idx].error = result.error || "Transaction rolled back.";
      }
      
      setMessages(finalized);
    } catch (err: any) {
      const finalized = [...messages];
      finalized[idx].is_executing = false;
      finalized[idx].requires_confirmation = false;
      finalized[idx].text = "Failed connecting to database executor.";
      finalized[idx].error = err.message;
      setMessages(finalized);
    }
  };

  const handleCancelModification = (idx: number) => {
    const updated = [...messages];
    updated[idx].requires_confirmation = false;
    updated[idx].canceled = true;
    updated[idx].text = "Database modification operation was canceled by the user.";
    setMessages(updated);
  };

  // Reopen query history offline
  const handleReopenHistory = (item: any) => {
    let records: any[] = [];
    try {
      records = item.result_json ? JSON.parse(item.result_json) : [];
    } catch (e) {
      console.error("Records parse failed:", e);
    }

    setMessages((prev) => [
      ...prev,
      {
        sender: "user",
        text: item.question
      },
      {
        sender: "ai",
        text: item.summary,
        question: item.question,
        sql: item.generated_sql,
        records: records,
        activeTab: "table",
        chartType: "bar"
      }
    ]);
  };

  const handleDeleteHistory = async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    try {
      await deleteHistoryItem(id);
      loadHistoryLogs();
    } catch (err: any) {
      alert("Delete history failed: " + err.message);
    }
  };

  const handleClearAllHistory = async () => {
    if (!confirm("Are you sure you want to clear all query history?")) return;
    try {
      await clearHistory();
      setHistoryList([]);
    } catch (err: any) {
      alert("Clear history failed: " + err.message);
    }
  };

  const handleExportPDF = async (msg: Message) => {
    try {
      await downloadActivePDF(msg.question || "Query", msg.text, msg.sql || "", msg.records || []);
    } catch (e: any) {
      alert("PDF generation failed: " + e.message);
    }
  };

  const handleExportExcel = async (records: any[]) => {
    try {
      await downloadActiveExcel(records);
    } catch (e: any) {
      alert("Excel generation failed: " + e.message);
    }
  };

  const handleExportCSV = async (records: any[]) => {
    try {
      await downloadActiveCSV(records);
    } catch (e: any) {
      alert("CSV export failed: " + e.message);
    }
  };

  const handleSaveAsReport = async (idx: number, msg: Message) => {
    if (!reportTitle.trim()) return;
    try {
      setSavingReport(true);
      await createReport(
        reportTitle.trim(),
        activeTableName,
        msg.question || "Query",
        msg.sql || "",
        msg.text,
        msg.records || []
      );
      
      const updated = [...messages];
      updated[idx].reportSaved = true;
      setMessages(updated);
      setSaveReportIdx(null);
      setReportTitle("");
    } catch (e: any) {
      alert("Failed saving report: " + e.message);
    } finally {
      setSavingReport(false);
    }
  };

  return (
    <div id="chat" className="bg-white border border-warmgray-100 rounded-2xl p-4 shadow-sm flex flex-col h-[520px]">
      <div className="border-b border-warmgray-100 pb-3 mb-3 flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <div className="bg-terracotta-50 border border-terracotta-100 p-2 rounded-xl text-terracotta-600">
            <Brain size={18} className="animate-pulse text-terracotta-500" />
          </div>
          <div>
            <h2 className="text-base font-bold text-warmgray-900">
              AI Analytics Chat
            </h2>
            <p className="text-warmgray-500 text-[10px] mt-0.5 font-semibold">
              Ask questions to query database, generate tables & charts
            </p>
          </div>
        </div>

        <button
          onClick={() => setShowHistory(!showHistory)}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-xl border text-[10px] font-bold cursor-pointer transition ${
            showHistory 
              ? "bg-terracotta-50 border-terracotta-200 text-terracotta-700" 
              : "bg-white border-warmgray-150 hover:bg-warmgray-50 text-warmgray-600"
          }`}
        >
          <History size={12} />
          <span>History Logs</span>
        </button>
      </div>

      <div className="flex-1 flex gap-4 overflow-hidden mb-3">
        <div className="flex-1 overflow-y-auto pr-1 space-y-4">
          {messages.map((msg, idx) => (
            <div
              key={idx}
              className={`flex gap-3 ${msg.sender === "user" ? "justify-end" : "justify-start"}`}
            >
              {msg.sender === "ai" && (
                <div className="w-8 h-8 bg-gradient-to-br from-terracotta-500 to-terracotta-600 text-white rounded-xl flex items-center justify-center shadow-md shadow-terracotta-500/10 shrink-0">
                  <Brain size={16} />
                </div>
              )}

              <div className={`max-w-[85%] space-y-2.5 ${msg.sender === "user" ? "text-right" : "text-left"}`}>
                {/* Regular Message Text */}
                <div
                  className={`p-4 rounded-2xl text-xs leading-relaxed ${
                    msg.sender === "user"
                      ? "bg-warmgray-950 text-white rounded-tr-sm"
                      : msg.canceled
                      ? "bg-warmgray-50 text-warmgray-400 border border-warmgray-150 border-dashed"
                      : "bg-warmgray-50/80 text-warmgray-850 rounded-tl-sm border border-warmgray-100/50"
                  }`}
                >
                  <p className="whitespace-pre-wrap font-medium">{msg.text}</p>

                  {/* Warning tags */}
                  {msg.warning && msg.requires_confirmation && (
                    <div className="mt-2.5 bg-terracotta-50 border border-terracotta-200 text-terracotta-800 rounded-xl p-3 flex gap-2 items-start font-semibold text-[10.5px]">
                      <AlertTriangle size={14} className="text-terracotta-500 shrink-0 mt-0.5" />
                      <span>{msg.warning}</span>
                    </div>
                  )}

                  {/* Diagnostic Error Box */}
                  {msg.error && (
                    <div className="mt-2.5 bg-red-50 border border-red-200 text-red-800 rounded-xl p-3 font-mono text-[10px] text-left">
                      <span className="font-bold block mb-0.5">Execution Failure:</span>
                      {msg.error}
                    </div>
                  )}

                  {/* Success metrics */}
                  {!msg.requires_confirmation && msg.rows_affected !== undefined && (
                    <div className="mt-3 pt-2.5 border-t border-warmgray-200/50 flex gap-4 text-[9.5px] font-bold text-warmgray-400">
                      <span>Rows affected: <strong className="text-warmgray-850">{msg.rows_affected}</strong></span>
                      <span>Execution time: <strong className="text-warmgray-850">{msg.execution_time_ms} ms</strong></span>
                    </div>
                  )}
                </div>

                {/* SQL Code Block Preview */}
                {msg.sql && !msg.canceled && (
                  <div className="bg-warmgray-950 rounded-xl border border-warmgray-900 overflow-hidden shadow-inner text-left font-mono text-[11px]">
                    <div className="bg-warmgray-900 px-3.5 py-1.5 border-b border-warmgray-950 flex justify-between items-center text-warmgray-400">
                      <span className="flex items-center gap-1 font-bold text-[9px] tracking-wide uppercase text-terracotta-400">
                        <Database size={10} /> SQL Statement Preview
                      </span>
                      <button
                        onClick={() => handleCopy(msg.sql!)}
                        className="hover:text-white p-1 rounded transition flex items-center gap-1 cursor-pointer text-[9px]"
                      >
                        {copiedSql === msg.sql ? <Check size={10} className="text-emerald-500" /> : <Copy size={10} />}
                        <span>{copiedSql === msg.sql ? "Copied" : "Copy"}</span>
                      </button>
                    </div>
                    <pre className="p-3 text-terracotta-300 overflow-x-auto whitespace-pre">
                      <code>{msg.sql}</code>
                    </pre>
                  </div>
                )}

                {/* DML/DDL Confirmation Dialog Buttons */}
                {msg.requires_confirmation && (
                  <div className="bg-warmgray-50 border border-warmgray-200/60 rounded-xl p-3 flex flex-col gap-2.5 text-left border-l-4 border-l-terracotta-500 shadow-sm">
                    <p className="text-[10px] font-bold text-warmgray-800">
                      This operation modifies database data or structures. Explicit approval is required.
                    </p>
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleConfirmModification(idx, msg)}
                        disabled={msg.is_executing}
                        className="bg-terracotta-500 hover:bg-terracotta-600 disabled:bg-terracotta-300 text-white px-3.5 py-1.5 rounded-lg text-[10px] font-bold transition flex items-center gap-1 cursor-pointer shadow-sm shadow-terracotta-500/10"
                      >
                        {msg.is_executing ? (
                          <Loader2 size={12} className="animate-spin" />
                        ) : (
                          <Play size={10} className="fill-white" />
                        )}
                        <span>{msg.is_executing ? "Executing..." : "Confirm & Execute"}</span>
                      </button>
                      <button
                        onClick={() => handleCancelModification(idx)}
                        disabled={msg.is_executing}
                        className="bg-white border border-warmgray-250 hover:bg-warmgray-50 text-warmgray-600 px-3 py-1.5 rounded-lg text-[10px] font-bold cursor-pointer disabled:opacity-50"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}

                {/* SQL statements actions bar */}
                {msg.sql && !msg.canceled && (
                  <div className="border border-warmgray-100/80 rounded-xl bg-white overflow-hidden shadow-sm text-left">
                    <div className="bg-warmgray-50 border-b border-warmgray-100 px-3 py-2 flex items-center justify-between flex-wrap gap-2">
                      <div className="flex gap-1.5">
                        {msg.records && msg.records.length > 0 && (
                          <>
                            <button
                              onClick={() => {
                                const updated = [...messages];
                                updated[idx].activeTab = "table";
                                setMessages(updated);
                              }}
                              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold transition cursor-pointer ${
                                msg.activeTab === "table"
                                  ? "bg-white text-warmgray-900 border border-warmgray-150 shadow-sm"
                                  : "text-warmgray-500 hover:text-warmgray-850"
                              }`}
                            >
                              <Table size={10} className="text-terracotta-500" /> Table View
                            </button>
                            
                            <button
                              onClick={() => {
                                const updated = [...messages];
                                updated[idx].activeTab = "chart";
                                setMessages(updated);
                              }}
                              className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[10px] font-bold transition cursor-pointer ${
                                msg.activeTab === "chart"
                                  ? "bg-white text-warmgray-900 border border-warmgray-150 shadow-sm"
                                  : "text-warmgray-500 hover:text-warmgray-850"
                              }`}
                            >
                              <BarChart3 size={10} className="text-terracotta-500" /> Chart View
                            </button>
                          </>
                        )}
                      </div>

                      <div className="flex items-center gap-1.5 flex-wrap">
                        <button
                          onClick={() => handleExportPDF(msg)}
                          className="flex items-center gap-1 text-warmgray-500 hover:text-warmgray-900 border border-warmgray-100 hover:bg-white px-2 py-1 rounded-md text-[9px] font-bold cursor-pointer transition"
                          title="Export PDF Report"
                        >
                          <Download size={9} className="text-terracotta-500" /> PDF
                        </button>
                        {msg.records && msg.records.length > 0 && (
                          <>
                            <button
                              onClick={() => handleExportExcel(msg.records!)}
                              className="flex items-center gap-1 text-warmgray-500 hover:text-warmgray-900 border border-warmgray-100 hover:bg-white px-2 py-1 rounded-md text-[9px] font-bold cursor-pointer transition"
                              title="Export Excel"
                            >
                              <Download size={9} className="text-terracotta-500" /> Excel
                            </button>
                            <button
                              onClick={() => handleExportCSV(msg.records!)}
                              className="flex items-center gap-1 text-warmgray-500 hover:text-warmgray-900 border border-warmgray-100 hover:bg-white px-2 py-1 rounded-md text-[9px] font-bold cursor-pointer transition"
                              title="Export CSV"
                            >
                              <Download size={9} className="text-terracotta-500" /> CSV
                            </button>
                          </>
                        )}

                        <button
                          onClick={() => {
                            if (msg.reportSaved) return;
                            setSaveReportIdx(saveReportIdx === idx ? null : idx);
                            setReportTitle(msg.question ? `Report - ${msg.question.slice(0, 30)}` : "My Report");
                          }}
                          disabled={msg.reportSaved}
                          className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-[9px] font-bold cursor-pointer transition border ${
                            msg.reportSaved
                              ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                              : "bg-white border-warmgray-150 hover:bg-warmgray-50 text-warmgray-600 hover:text-terracotta-600"
                          }`}
                        >
                          <FolderHeart size={9} className={msg.reportSaved ? "text-emerald-500" : "text-terracotta-500"} />
                          <span>{msg.reportSaved ? "Saved!" : "Save Report"}</span>
                        </button>
                      </div>
                    </div>

                    {/* Inline Save Report */}
                    {saveReportIdx === idx && (
                      <div className="bg-warmgray-50 border-b border-warmgray-100 p-2.5 flex items-center justify-between gap-2 text-[10px] font-bold">
                        <input
                          type="text"
                          value={reportTitle}
                          onChange={(e) => setReportTitle(e.target.value)}
                          placeholder="Enter report title..."
                          className="flex-1 bg-white border border-warmgray-200 rounded px-2 py-1 focus:outline-none focus:border-terracotta-400 font-bold"
                        />
                        <div className="flex gap-1">
                          <button
                            onClick={() => handleSaveAsReport(idx, msg)}
                            disabled={savingReport || !reportTitle.trim()}
                            className="bg-terracotta-500 hover:bg-terracotta-600 text-white px-2.5 py-1 rounded cursor-pointer disabled:opacity-50 flex items-center gap-0.5"
                          >
                            {savingReport && <Loader2 size={10} className="animate-spin" />}
                            <span>Save</span>
                          </button>
                          <button
                            onClick={() => {
                              setSaveReportIdx(null);
                              setReportTitle("");
                            }}
                            disabled={savingReport}
                            className="bg-white border border-warmgray-200 hover:bg-warmgray-100 px-2 py-1 rounded text-warmgray-600 cursor-pointer"
                          >
                            Cancel
                          </button>
                        </div>
                      </div>
                    )}

                    {msg.activeTab === "table" && msg.records && (
                      <InnerTable records={msg.records} />
                    )}

                    {msg.activeTab === "chart" && msg.records && (
                      <InnerChart records={msg.records} type={msg.chartType || "bar"} onChangeType={(type) => {
                        const updated = [...messages];
                        updated[idx].chartType = type;
                        setMessages(updated);
                      }} />
                    )}
                  </div>
                )}
              </div>

              {/* User Avatar */}
              {msg.sender === "user" && (
                <div className="w-8 h-8 bg-warmgray-100 text-warmgray-850 rounded-xl flex items-center justify-center font-bold text-xs shrink-0 border border-warmgray-200 shadow-inner select-none">
                  U
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div className="flex gap-3 justify-start">
              <div className="w-8 h-8 bg-terracotta-500 text-white rounded-xl flex items-center justify-center shadow-md animate-pulse">
                <Brain size={16} />
              </div>
              <div className="bg-warmgray-50 rounded-2xl p-4 border border-warmgray-100/50 max-w-sm flex items-center gap-2">
                <div className="w-3.5 h-3.5 border-2 border-terracotta-500 border-t-transparent rounded-full animate-spin" />
                <span className="text-warmgray-500 text-xs font-semibold">Generating query...</span>
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* History sidebar drawer */}
        {showHistory && (
          <div className="w-60 border-l border-warmgray-100 pl-3 flex flex-col h-full shrink-0 overflow-hidden animate-fade-in">
            <div className="flex justify-between items-center pb-2 border-b border-warmgray-100 mb-2">
              <span className="text-[10px] font-bold text-warmgray-900 flex items-center gap-1 uppercase tracking-wide">
                <History size={12} className="text-terracotta-500" /> Query History
              </span>
              {historyList.length > 0 && (
                <button
                  onClick={handleClearAllHistory}
                  className="text-[9px] font-bold text-red-500 hover:text-red-650 cursor-pointer"
                >
                  Clear All
                </button>
              )}
            </div>

            {loadingHistory && historyList.length === 0 ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 className="animate-spin text-terracotta-500" size={20} />
              </div>
            ) : historyList.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center text-warmgray-400 p-2">
                <History size={16} className="text-warmgray-300 mb-0.5" />
                <span className="text-[9px] font-bold text-warmgray-500">No query logs yet</span>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                {historyList.map((item) => (
                  <div
                    key={item.id}
                    onClick={() => handleReopenHistory(item)}
                    className="p-2 bg-warmgray-50 hover:bg-terracotta-50/20 border border-warmgray-100 hover:border-terracotta-200 rounded-lg cursor-pointer transition text-left relative group/item"
                    title="Click to reopen query results instantly"
                  >
                    <p className="text-[10px] font-bold text-warmgray-900 line-clamp-2 pr-4 leading-tight">
                      {item.question}
                    </p>
                    <div className="flex justify-between items-center mt-1.5 text-[8.5px] text-warmgray-450 font-bold">
                      <span>{item.result_count} records</span>
                      <span>{new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>

                    <button
                      onClick={(e) => handleDeleteHistory(e, item.id)}
                      className="absolute top-1 right-1 p-0.5 rounded hover:bg-red-50 text-warmgray-400 hover:text-red-500 opacity-0 group-hover/item:opacity-100 transition cursor-pointer"
                      title="Delete log"
                    >
                      <Trash2 size={10} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input Form */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          askAI();
        }}
        className="border border-warmgray-100 rounded-xl p-2 bg-warmgray-50/50 flex gap-2 items-center focus-within:border-terracotta-500 transition-colors"
      >
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              askAI();
            }
          }}
          placeholder="Ask anything about your data..."
          rows={1}
          className="flex-1 bg-transparent resize-none focus:outline-none pl-2.5 pr-2 py-1.5 text-xs text-warmgray-900 placeholder-warmgray-400 font-semibold"
        />

        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="bg-terracotta-500 hover:bg-terracotta-600 text-white p-2.5 rounded-lg transition duration-200 disabled:opacity-40 disabled:scale-100 hover:scale-105 active:scale-95 cursor-pointer shrink-0"
        >
          <Send size={14} />
        </button>
      </form>
    </div>
  );
}

// Inner Component for Table Pagination
function InnerTable({ records }: { records: Record<string, any>[] }) {
  const [currentPage, setCurrentPage] = useState(1);
  const [search, setSearch] = useState("");
  const itemsPerPage = 5;

  const columns = Object.keys(records[0] || {});

  const filtered = records.filter(row => 
    Object.values(row).some(v => String(v).toLowerCase().includes(search.toLowerCase()))
  );

  const totalPages = Math.ceil(filtered.length / itemsPerPage);
  const start = (currentPage - 1) * itemsPerPage;
  const paginated = filtered.slice(start, start + itemsPerPage);

  return (
    <div className="p-3 space-y-2.5">
      {records.length > 5 && (
        <div className="relative">
          <Search className="absolute left-2 top-1/2 -translate-y-1/2 text-warmgray-400" size={12} />
          <input
            type="text"
            placeholder="Search query results..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setCurrentPage(1);
            }}
            className="w-full bg-slate-50 border border-warmgray-100 rounded-md pl-7 pr-2 py-1 text-[10px] focus:outline-none focus:border-terracotta-400 focus:bg-white text-warmgray-900 font-semibold"
          />
        </div>
      )}

      <div className="overflow-x-auto border border-warmgray-100/50 rounded-lg">
        <table className="min-w-full text-[10px] text-warmgray-850">
          <thead className="bg-warmgray-50 border-b border-warmgray-100/40">
            <tr>
              {columns.map(c => (
                <th key={c} className="px-2.5 py-1.5 font-bold text-warmgray-905 text-left uppercase whitespace-nowrap text-[9px]">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-warmgray-50/50 bg-white">
            {paginated.map((row, rIdx) => (
              <tr key={rIdx} className="hover:bg-warmgray-50/30">
                {columns.map(c => (
                  <td key={c} className="px-2.5 py-1.5 text-warmgray-900 font-semibold truncate max-w-[150px]">
                    {row[c] === null ? "null" : String(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-[9px] text-warmgray-500 font-bold">
        <span>Rows: {filtered.length} total</span>
        {totalPages > 1 && (
          <div className="flex gap-1.5">
            <button
              onClick={() => setCurrentPage(p => Math.max(p - 1, 1))}
              disabled={currentPage === 1}
              className="p-0.5 border border-warmgray-200 rounded disabled:opacity-40"
            >
              <ChevronLeft size={10} />
            </button>
            <span className="flex items-center">
              {currentPage} / {totalPages}
            </span>
            <button
              onClick={() => setCurrentPage(p => Math.min(p + 1, totalPages))}
              disabled={currentPage === totalPages}
              className="p-0.5 border border-warmgray-200 rounded disabled:opacity-40"
            >
              <ChevronRight size={10} />
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// Inner SVG Chart Renderer Component
function InnerChart({ 
  records,
  type = "bar",
  onChangeType
}: { 
  records: Record<string, any>[];
  type: "bar" | "line";
  onChangeType: (type: "bar" | "line") => void;
}) {
  const keys = Object.keys(records[0] || {});
  
  let valueKey = keys.find(k => typeof records[0][k] === "number");
  let labelKey = keys.find(k => k !== valueKey);

  if (!valueKey) {
    valueKey = keys.find(k => !isNaN(parseFloat(records[0][k])));
  }
  if (!labelKey) {
    labelKey = keys[0];
  }

  if (!valueKey) {
    return (
      <div className="p-4 text-center text-[10px] text-warmgray-450 font-bold">
        <Info size={14} className="mx-auto mb-1 text-warmgray-450" />
        No numeric columns found to construct visualization.
      </div>
    );
  }

  const cleanRecords = records.slice(0, 10);
  const labels = cleanRecords.map(r => String(r[labelKey!] ?? "Unknown"));
  const values = cleanRecords.map(r => {
    const v = parseFloat(r[valueKey!]);
    return isNaN(v) ? 0 : v;
  });

  const maxValue = Math.max(...values, 1);
  const minValue = Math.min(...values, 0);
  const range = maxValue - minValue;

  const width = 500;
  const height = 180;
  const paddingLeft = 65;
  const paddingRight = 15;
  const paddingTop = 15;
  const paddingBottom = 30;

  const graphWidth = width - paddingLeft - paddingRight;
  const graphHeight = height - paddingTop - paddingBottom;

  const points = cleanRecords.map((_, idx) => {
    const x = paddingLeft + (idx * (graphWidth / (cleanRecords.length - 1 || 1)));
    const ratio = range === 0 ? 0.5 : (values[idx] - minValue) / range;
    const y = paddingTop + graphHeight - (ratio * graphHeight);
    return { x, y, label: labels[idx], value: values[idx] };
  });

  return (
    <div className="p-3 space-y-3">
      <div className="flex justify-between items-center text-[10px] font-bold">
        <span className="text-warmgray-850">
          Visual: {valueKey} by {labelKey} {records.length > 10 && <span className="text-[9px] font-normal text-warmgray-400">(Top 10 shown)</span>}
        </span>
        <div className="flex border border-warmgray-200 rounded-md overflow-hidden bg-warmgray-50 p-0.5">
          <button
            onClick={() => onChangeType("bar")}
            className={`p-0.5 px-2 text-[9px] font-bold cursor-pointer ${
              type === "bar" ? "bg-white text-warmgray-900 shadow-sm border border-warmgray-100" : "bg-transparent text-warmgray-500 hover:text-warmgray-800"
            }`}
          >
            Bar
          </button>
          <button
            onClick={() => onChangeType("line")}
            className={`p-0.5 px-2 text-[9px] font-bold cursor-pointer ${
              type === "line" ? "bg-white text-warmgray-900 shadow-sm border border-warmgray-100" : "bg-transparent text-warmgray-500 hover:text-warmgray-800"
            }`}
          >
            Line
          </button>
        </div>
      </div>

      <div className="bg-warmgray-50 border border-warmgray-100 rounded-xl p-2.5 flex justify-center">
        <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className="max-w-[420px]">
          {[0, 0.25, 0.5, 0.75, 1].map((ratio, gridIdx) => {
            const y = paddingTop + graphHeight - ratio * graphHeight;
            const gridVal = minValue + ratio * range;
            return (
              <g key={gridIdx}>
                <line
                  x1={paddingLeft}
                  y1={y}
                  x2={width - paddingRight}
                  y2={y}
                  stroke="#e8e2da"
                  strokeWidth="1"
                  strokeDasharray="4 4"
                />
                <text
                  x={paddingLeft - 8}
                  y={y + 3}
                  textAnchor="end"
                  fill="#bd9f8d"
                  fontSize="8"
                  fontFamily="monospace"
                  fontWeight="bold"
                >
                  {gridVal >= 1000000 
                    ? (gridVal / 1000000).toFixed(1) + "M"
                    : gridVal >= 1000
                    ? (gridVal / 1000).toFixed(0) + "k"
                    : gridVal.toFixed(0)}
                </text>
              </g>
            );
          })}

          {type === "bar" && 
            points.map((pt, barIdx) => {
              const barWidth = Math.max(graphWidth / points.length * 0.5, 6);
              const barX = pt.x - barWidth / 2;
              const barY = pt.y;
              const barHeight = paddingTop + graphHeight - pt.y;

              return (
                <g key={barIdx} className="group">
                  <rect
                    x={barX}
                    y={barY}
                    width={barWidth}
                    height={Math.max(barHeight, 2)}
                    rx="2"
                    className="fill-terracotta-500 hover:fill-terracotta-600 transition-all duration-300"
                  />
                  <title>{`${pt.label}: ${pt.value.toLocaleString()}`}</title>
                  <text
                    x={pt.x}
                    y={height - 15}
                    textAnchor="middle"
                    fill="#a07f6b"
                    fontSize="7"
                    fontWeight="bold"
                    transform={`rotate(-15, ${pt.x}, ${height - 15})`}
                  >
                    {pt.label.length > 7 ? pt.label.slice(0, 6) + ".." : pt.label}
                  </text>
                </g>
              );
            })
          }

          {type === "line" && (
            <g>
              <defs>
                <linearGradient id="terracottaGradSmall" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#C35237" stopOpacity="0.2" />
                  <stop offset="100%" stopColor="#C35237" stopOpacity="0.0" />
                </linearGradient>
              </defs>
              
              <path
                d={`${points.map((pt, ptIdx) => `${ptIdx === 0 ? "M" : "L"} ${pt.x} ${pt.y}`).join(" ")} L ${points[points.length-1].x} ${paddingTop+graphHeight} L ${points[0].x} ${paddingTop+graphHeight} Z`}
                fill="url(#terracottaGradSmall)"
              />

              <path
                d={points.map((pt, ptIdx) => `${ptIdx === 0 ? "M" : "L"} ${pt.x} ${pt.y}`).join(" ")}
                fill="none"
                stroke="#C35237"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              
              {points.map((pt, circleIdx) => (
                <g key={circleIdx} className="group">
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r="3.5"
                    className="fill-white stroke-terracotta-500 stroke-2 hover:fill-terracotta-600 transition-all"
                  />
                  <title>{`${pt.label}: ${pt.value.toLocaleString()}`}</title>
                  <text
                    x={pt.x}
                    y={height - 15}
                    textAnchor="middle"
                    fill="#a07f6b"
                    fontSize="7"
                    fontWeight="bold"
                    transform={`rotate(-15, ${pt.x}, ${height - 15})`}
                  >
                    {pt.label.length > 7 ? pt.label.slice(0, 6) + ".." : pt.label}
                  </text>
                </g>
              ))}
            </g>
          )}
        </svg>
      </div>
    </div>
  );
}