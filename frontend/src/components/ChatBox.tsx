import { useState, useRef, useEffect } from "react";
import { 
  Send, 
  Copy, 
  Check, 
  Database, 
  Download, 
  Table, 
  ChevronLeft, 
  ChevronRight, 
  Search, 
  Info, 
  History, 
  Trash2, 
  FolderHeart, 
  Loader2, 
  AlertTriangle,
  AlertCircle, 
  Play,
  Sparkles,
  BarChart3,
  RotateCcw
} from "lucide-react";

import { 
  getHistory, 
  deleteHistoryItem, 
  clearHistory, 
  createReport,
  downloadActivePDF,
  downloadActiveExcel,
  downloadActiveCSV,
  askModification,
  executeModification,
  cancelModification,
  askQuestion,
  undoHistoryItem
} from "../services/api";

interface Message {
  sender: "user" | "ai";
  text: string;
  question?: string;
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
  target_dataset?: string;
  confirmation_token?: string;
  estimated_rows?: number;
  expires_at?: string;
  is_executing?: boolean;
  rows_affected?: number;
  execution_time_ms?: number;
  canceled?: boolean;
  history_id?: number;
  is_undone?: boolean;
  is_undoing?: boolean;
  needs_clarification?: boolean;
  clarification_options?: string[];
  clarification_context?: Record<string, any>;

  // Conversational Bulk Record Preview properties
  is_bulk_insert?: boolean;
  total_records?: number;
  valid_records_count?: number;
  invalid_records_count?: number;
  preview_columns?: string[];
  preview_records?: Record<string, any>[];
  invalid_records?: Array<{ record_index: number; raw_record?: any; reason: string }>;
  missing_fields?: string[];
}

interface ChatBoxProps {
  messages: Message[];
  setMessages: React.Dispatch<React.SetStateAction<Message[]>>;
  question: string;
  setQuestion: (q: string) => void;
}

// Safely format basic markdown elements (**bold**, `code`, - bullet lists) into HTML
function formatMessageText(text: string): string {
  if (!text) return "";
  
  // 1. Escape HTML characters to protect against any injection
  let escaped = text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");

  // 2. Parse bold text: **text** -> <strong>text</strong>
  escaped = escaped.replace(/\*\*(.*?)\*\*/g, "<strong class=\"font-semibold text-[#172B4D]\">$1</strong>");

  // 3. Parse inline code snippets: `code` -> <code class="...">code</code>
  escaped = escaped.replace(/`(.*?)`/g, '<code class="bg-[#168C88]/10 text-[#168C88] px-1.5 py-0.5 rounded font-mono text-[10px] font-semibold">$1</code>');

  // 4. Parse line-by-line bullet points
  const lines = escaped.split("\n");
  const formattedLines = lines.map(line => {
    const trimmed = line.trim();
    if (trimmed.startsWith("- ") || trimmed.startsWith("* ")) {
      const content = trimmed.substring(2);
      return `<li class="list-disc ml-4 mt-0.5 text-[#172B4D]">${content}</li>`;
    }
    return line;
  });
  
  return formattedLines.join("<br/>");
}

export default function ChatBox({ messages, setMessages, question, setQuestion }: ChatBoxProps) {
  const [loading, setLoading] = useState(false);
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
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const dataset = JSON.parse(sessionStorage.getItem("dataset") || "{}");
  const activeTableName = dataset?.filename || "Active Dataset";

  // Filter out any stale generic greeting messages if present
  const displayMessages = messages.filter(
    (m) => !(m.sender === "ai" && m.text.includes("Hello! I am your AI Analytics Assistant"))
  );

  useEffect(() => {
    // Check if user came from Custom Table Builder with a seed prompt
    const seed = sessionStorage.getItem("seed_chat_prompt");
    if (seed) {
      setQuestion(seed);
      sessionStorage.removeItem("seed_chat_prompt");
      textareaRef.current?.focus();
    }
  }, []);

  useEffect(() => {
    if (displayMessages.length === 0 && !loading) return;
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [displayMessages.length, loading]);

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

  const askAI = async (overrideText?: string, clarificationCtx?: Record<string, any>) => {
    const textToSend = overrideText || question;
    if (!textToSend.trim()) return;

    const currentQuestion = textToSend;
    if (!overrideText) setQuestion("");
    setLoading(true);

    // Append user question
    setMessages((prev) => [
      ...prev,
      { sender: "user", text: currentQuestion }
    ]);

    try {
      // 1. Intercept user question by calling intent detector and preview generator
      const modCheck = await askModification(currentQuestion);

      if (modCheck.needs_clarification) {
        setMessages((prev) => [
          ...prev,
          {
            sender: "ai",
            text: modCheck.message || "Please clarify which table you would like to insert records into:",
            needs_clarification: true,
            clarification_options: modCheck.clarification_options
          }
        ]);
        setLoading(false);
        return;
      }

      if (modCheck.requires_confirmation) {
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
            target_dataset: modCheck.target_dataset || modCheck.table_name,
            confirmation_token: modCheck.confirmation_token,
            estimated_rows: modCheck.estimated_rows,
            expires_at: modCheck.expires_at,
            records: [],
            // Structured Bulk Insertion Preview
            is_bulk_insert: modCheck.is_bulk_insert,
            total_records: modCheck.total_records,
            valid_records_count: modCheck.valid_records_count,
            invalid_records_count: modCheck.invalid_records_count,
            preview_columns: modCheck.preview_columns,
            preview_records: modCheck.preview_records,
            invalid_records: modCheck.invalid_records,
            missing_fields: modCheck.missing_fields
          }
        ]);
        setLoading(false);
        return;
      }

      if (modCheck.error) {
        // The modification query failed safety validation or record parsing
        setMessages((prev) => [
          ...prev,
          {
            sender: "ai",
            text: "I couldn't complete that modification:",
            error: modCheck.error || "Validation failed.",
            invalid_records: modCheck.invalid_records || []
          }
        ]);
        setLoading(false);
        return;
      }

      // 2. If it is standard SELECT, proceed through the read-only ask router
      const data = await askQuestion(currentQuestion, overrideText ? currentQuestion : undefined, clarificationCtx);

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
          chartType: "bar",
          needs_clarification: data.needs_clarification,
          clarification_options: data.clarification_options,
          clarification_context: data.clarification_context
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
    if (!msg.confirmation_token) {
      const finalized = [...messages];
      finalized[idx].is_executing = false;
      finalized[idx].requires_confirmation = false;
      finalized[idx].text = "Missing server confirmation token. Please request a new preview.";
      finalized[idx].error = "Missing confirmation token.";
      setMessages(finalized);
      return;
    }

    try {
      const updating = [...messages];
      updating[idx].is_executing = true;
      setMessages(updating);

      const result = await executeModification(
        msg.sql || "",
        msg.intent || "",
        msg.table_name || "",
        msg.question || "",
        msg.confirmation_token
      );

      const finalized = [...messages];
      finalized[idx].is_executing = false;
      finalized[idx].requires_confirmation = false;

      if (result.success) {
        finalized[idx].text = result.message || "Modification executed successfully.";
        finalized[idx].rows_affected = result.rows_affected;
        finalized[idx].execution_time_ms = result.execution_time_ms;
        finalized[idx].records = result.records || [];
        finalized[idx].history_id = result.history_id;
        
        window.dispatchEvent(new Event("dataset-modified"));
        loadHistoryLogs();
      } else {
        finalized[idx].text = "Database execution failed. The transaction was automatically rolled back.";
        finalized[idx].error = result.error || "Transaction rolled back.";
      }
      
      setMessages(finalized);
    } catch (err: any) {
      const finalized = [...messages];
      finalized[idx].is_executing = false;
      finalized[idx].requires_confirmation = false;
      finalized[idx].text = "Execution failed. Transaction was not applied.";
      finalized[idx].error = err.message || "Failed executing modification.";
      setMessages(finalized);
    }
  };

  const handleCancelModification = async (idx: number) => {
    const msg = messages[idx];
    if (msg?.confirmation_token) {
      try {
        await cancelModification(msg.confirmation_token);
      } catch (e) {
        // Safe fallback
      }
    }
    const updated = [...messages];
    updated[idx].requires_confirmation = false;
    updated[idx].canceled = true;
    updated[idx].text = "Database modification operation was canceled by the user.";
    setMessages(updated);
  };

  const handleUndo = async (idx: number, historyId: number) => {
    try {
      const updating = [...messages];
      updating[idx].is_undoing = true;
      setMessages(updating);

      const result = await undoHistoryItem(historyId);

      const finalized = [...messages];
      finalized[idx].is_undoing = false;
      
      if (result.success) {
        finalized[idx].is_undone = true;
        finalized[idx].text = "Database changes successfully rolled back! (Undone)";
        window.dispatchEvent(new Event("dataset-modified"));
        loadHistoryLogs();
      } else {
        finalized[idx].error = result.message || "Failed to undo change.";
      }
      setMessages(finalized);
    } catch (err: any) {
      const finalized = [...messages];
      finalized[idx].is_undoing = false;
      finalized[idx].error = err.message || "Failed to undo change.";
      setMessages(finalized);
    }
  };

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
    <div id="chat" className="bg-white border border-[#E2E8F0] rounded-[14px] p-3.5 sm:p-4 pb-3 sm:pb-3.5 shadow-[0_1px_3px_rgba(0,0,0,0.04)] flex flex-col h-[540px]">
      {/* 1. Header */}
      <div className="border-b border-[#E2E8F0] pb-3 mb-3 flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-[#168C88]/10 border border-[#168C88]/20 flex items-center justify-center text-[#168C88] shrink-0">
            <BarChart3 size={17} strokeWidth={2.2} />
          </div>
          <h2 className="text-sm sm:text-base font-semibold text-[#172B4D] tracking-tight">
            Analytics Workspace
          </h2>
        </div>

        {/* Header Right Actions */}
        <div className="flex items-center gap-2">
          {displayMessages.length > 0 && (
            <button
              onClick={() => setMessages([])}
              className="flex items-center gap-1 px-2.5 py-1.5 rounded-lg border border-[#E2E8F0] text-xs font-medium text-[#64748B] hover:text-[#172B4D] hover:bg-[#F8FAFC] cursor-pointer transition"
              title="Start a new analysis session"
            >
              <RotateCcw size={12} />
              <span className="hidden sm:inline">New Analysis</span>
            </button>
          )}

          <button
            onClick={() => setShowHistory(!showHistory)}
            className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-xs font-bold cursor-pointer transition ${
              showHistory 
                ? "bg-[#FF5722] text-white border-[#FF5722] shadow-sm shadow-[#FF5722]/30" 
                : "bg-white border-[#FF5722]/50 text-[#FF5722] hover:bg-[#FF5722]/10"
            }`}
            title={showHistory ? "Close query history" : "Open query history"}
          >
            <History size={13} className={showHistory ? "text-white" : "text-[#FF5722]"} />
            <span>History Logs</span>
            {historyList.length > 0 && (
              <span className={`ml-0.5 px-1.5 py-0.2 rounded-full text-[10px] font-bold ${
                showHistory ? "bg-white/25 text-white" : "bg-[#FF5722]/15 text-[#FF5722]"
              }`}>
                {historyList.length}
              </span>
            )}
          </button>
        </div>
      </div>

      {/* Main Workspace Body */}
      <div className="flex-1 flex gap-4 overflow-hidden mb-3">
        {/* Messages or Clean Centered Empty State */}
        <div className="flex-1 overflow-y-auto pr-1 space-y-4 flex flex-col">
          {displayMessages.length === 0 ? (
            /* 2. Compact Centered Empty State without cards */
            <div className="flex-1 flex flex-col items-center justify-center p-4 sm:p-6 text-center my-auto">
              <div className="w-11 h-11 rounded-xl bg-[#168C88]/10 border border-[#168C88]/20 flex items-center justify-center text-[#168C88] mb-3 shadow-xs">
                <Sparkles size={20} strokeWidth={2} />
              </div>
              
              <h3 className="text-base sm:text-lg font-semibold text-[#172B4D] tracking-tight">
                What would you like to analyze?
              </h3>
              <p className="text-xs text-[#64748B] mt-1 max-w-sm">
                Ask questions about your data in natural language.
              </p>
            </div>
          ) : (
            /* 3. Professional Chat Messages Interface */
            displayMessages.map((msg, idx) => (
              <div
                key={idx}
                className={`flex flex-col ${msg.sender === "user" ? "items-end" : "items-start"}`}
              >
                {/* User Message Card */}
                {msg.sender === "user" ? (
                  <div className="max-w-[85%] sm:max-w-[75%] space-y-1">
                    <span className="text-[10px] font-medium text-[#64748B] block text-right pr-1">
                      You
                    </span>
                    <div className="p-3 px-3.5 rounded-[12px] bg-[#F8FAFC] border border-[#E2E8F0] text-xs text-[#172B4D] shadow-xs text-left leading-relaxed">
                      <p className="whitespace-pre-wrap font-medium">{msg.text}</p>
                    </div>
                  </div>
                ) : (
                  /* Assistant Analysis Card */
                  <div className="w-full max-w-[92%] sm:max-w-[90%] space-y-1 text-left">
                    <div className="flex items-center gap-1.5 pl-1 mb-0.5">
                      <div className="w-4 h-4 rounded bg-[#168C88]/10 border border-[#168C88]/20 flex items-center justify-center text-[#168C88]">
                        <Sparkles size={10} />
                      </div>
                      <span className="text-[10px] font-semibold text-[#172B4D] tracking-wide">
                        Analytics Engine
                      </span>
                    </div>

                    <div className="bg-white border border-[#E2E8F0] rounded-[12px] p-4 shadow-xs space-y-3">
                      {/* Summary / Analysis Text */}
                      <div className="text-xs text-[#172B4D] leading-relaxed">
                        <p
                          className="whitespace-pre-wrap font-normal"
                          dangerouslySetInnerHTML={{ __html: formatMessageText(msg.text) }}
                        />
                      </div>

                      {/* Clarification Option Chips */}
                      {msg.needs_clarification && msg.clarification_options && msg.clarification_options.length > 0 && (
                        <div className="pt-2.5 border-t border-[#E2E8F0]">
                          <span className="text-[10px] font-semibold text-[#64748B] block mb-1.5 uppercase tracking-wide">
                            Clarify your query
                          </span>
                          <div className="flex flex-wrap gap-1.5">
                            {msg.clarification_options.map((opt, i) => (
                              <button
                                key={i}
                                onClick={() => askAI(opt, msg.clarification_context)}
                                className="px-2.5 py-1 bg-[#168C88]/10 hover:bg-[#168C88]/20 text-[#168C88] border border-[#168C88]/25 rounded-lg text-xs font-medium transition cursor-pointer active:scale-95 shadow-xs"
                              >
                                {opt}
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Warning Box */}
                      {msg.warning && msg.requires_confirmation && (
                        <div className="bg-amber-50 border border-amber-200 text-amber-900 rounded-lg p-2.5 flex gap-2 items-start text-xs font-medium">
                          <AlertTriangle size={14} className="text-amber-600 shrink-0 mt-0.5" />
                          <span>{msg.warning}</span>
                        </div>
                      )}

                      {/* Diagnostic Error Box */}
                      {msg.error && (
                        <div className="bg-red-50 border border-red-200 text-red-900 rounded-lg p-3 font-mono text-xs">
                          <span className="font-semibold block mb-0.5">Execution Failure:</span>
                          {msg.error}
                        </div>
                      )}

                      {/* SQL Code Block */}
                      {msg.sql && !msg.canceled && (
                        <div className="bg-[#0F172A] rounded-lg border border-[#1E293B] overflow-hidden shadow-inner font-mono text-[11px]">
                          <div className="bg-[#1E293B] px-3 py-1.5 border-b border-slate-700/60 flex justify-between items-center text-slate-300">
                            <span className="flex items-center gap-1.5 font-semibold text-[10px] tracking-wider uppercase text-[#168C88]">
                              <Database size={11} /> SQL Statement
                            </span>
                            <button
                              onClick={() => handleCopy(msg.sql!)}
                              className="hover:text-white px-2 py-0.5 rounded hover:bg-slate-700/50 transition flex items-center gap-1 cursor-pointer text-[10px] text-slate-300"
                            >
                              {copiedSql === msg.sql ? <Check size={11} className="text-emerald-400" /> : <Copy size={11} />}
                              <span>{copiedSql === msg.sql ? "Copied" : "Copy"}</span>
                            </button>
                          </div>
                          <pre className="p-3 text-slate-100 overflow-x-auto whitespace-pre leading-relaxed">
                            <code>{msg.sql}</code>
                          </pre>
                        </div>
                      )}

                      {/* DML/DDL Confirmation Dialog */}
                      {msg.requires_confirmation && (
                        <div className="bg-[#FFFBEB] border border-[#FDE68A] text-[#92400E] rounded-xl p-3.5 flex flex-col gap-3 shadow-xs">
                          {/* Header */}
                          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-amber-200/60 pb-2.5">
                            <div className="flex items-center gap-2">
                              <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-amber-100 text-amber-800 border border-amber-300">
                                {msg.is_bulk_insert ? "INSERT PREVIEW" : (msg.intent || "MODIFICATION")}
                              </span>
                              <span className="text-xs text-amber-950 font-bold">
                                {msg.is_bulk_insert 
                                  ? `${msg.preview_records?.length || 0} record(s) ready for insertion` 
                                  : (msg.target_dataset || msg.table_name)}
                              </span>
                            </div>
                            <div className="text-[11px] text-amber-900 font-mono">
                              Target Table: <strong className="text-amber-950">{msg.target_dataset || msg.table_name}</strong>
                            </div>
                          </div>

                          {/* Impact explanation */}
                          <p className="text-xs text-amber-950 font-medium leading-relaxed">
                            {msg.text || "This operation modifies stored data or structure. Explicit approval is required."}
                          </p>

                          {/* Structured Records Preview Table */}
                          {msg.preview_records && msg.preview_records.length > 0 && (
                            <div className="border border-amber-200/80 rounded-lg overflow-hidden bg-white shadow-xs">
                              <div className="bg-amber-50/80 px-3 py-1.5 border-b border-amber-200/60 flex items-center justify-between text-[11px] font-bold text-amber-900">
                                <span className="flex items-center gap-1.5 uppercase tracking-wider text-[10px]">
                                  <Table size={11} className="text-[#168C88]" /> Valid Records to Insert ({msg.preview_records.length})
                                </span>
                              </div>
                              <div className="overflow-x-auto max-h-56">
                                <table className="w-full text-left border-collapse text-xs">
                                  <thead>
                                    <tr className="bg-slate-50 border-b border-slate-200 text-slate-700 font-semibold text-[11px]">
                                      <th className="p-2 border-r border-slate-200 w-10 text-center font-mono">#</th>
                                      {(msg.preview_columns || Object.keys(msg.preview_records[0])).map((col) => (
                                        <th key={col} className="p-2 border-r border-slate-200 font-mono whitespace-nowrap">
                                          {col}
                                        </th>
                                      ))}
                                    </tr>
                                  </thead>
                                  <tbody className="divide-y divide-slate-100 text-slate-800">
                                    {msg.preview_records.map((row, rIdx) => (
                                      <tr key={rIdx} className="hover:bg-amber-50/30 transition-colors">
                                        <td className="p-2 border-r border-slate-200 text-center font-mono text-[10px] text-slate-400">
                                          {rIdx + 1}
                                        </td>
                                        {(msg.preview_columns || Object.keys(msg.preview_records![0])).map((col) => (
                                          <td key={col} className="p-2 border-r border-slate-200 font-mono text-xs whitespace-nowrap">
                                            {row[col] !== null && row[col] !== undefined ? String(row[col]) : <span className="text-slate-300 italic">NULL</span>}
                                          </td>
                                        ))}
                                      </tr>
                                    ))}
                                  </tbody>
                                </table>
                              </div>
                            </div>
                          )}

                          {/* Invalid Records Warning */}
                          {msg.invalid_records && msg.invalid_records.length > 0 && (
                            <div className="bg-red-50 border border-red-200 rounded-lg p-3 text-xs text-red-900 space-y-1.5">
                              <div className="font-bold flex items-center gap-1.5 text-red-800">
                                <AlertCircle size={13} className="text-red-600 shrink-0" />
                                <span>{msg.invalid_records.length} record(s) failed validation and will NOT be inserted:</span>
                              </div>
                              <ul className="list-disc pl-5 space-y-1 text-[11px] text-red-700">
                                {msg.invalid_records.map((inv, invIdx) => (
                                  <li key={invIdx}>
                                    <strong>Record #{inv.record_index}:</strong> {inv.reason}
                                  </li>
                                ))}
                              </ul>
                              <p className="text-[10px] text-red-600 font-medium pt-0.5">
                                Note: If you confirm, only the {msg.preview_records?.length || 0} valid record(s) listed above will be inserted into the database.
                              </p>
                            </div>
                          )}

                          {/* Missing / Omitted columns note */}
                          {msg.missing_fields && msg.missing_fields.length > 0 && (
                            <div className="text-[10px] text-amber-800/90 italic">
                              Unspecified optional columns left as NULL: {msg.missing_fields.join(", ")}
                            </div>
                          )}

                          {/* Action Buttons */}
                          <div className="flex gap-2 items-center pt-1">
                            <button
                              onClick={() => handleConfirmModification(idx, msg)}
                              disabled={msg.is_executing || (!msg.preview_records?.length && msg.is_bulk_insert)}
                              className="bg-[#168C88] hover:bg-[#137774] disabled:bg-[#168C88]/50 text-white px-3.5 py-2 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 cursor-pointer shadow-xs disabled:cursor-not-allowed"
                            >
                              {msg.is_executing ? (
                                <Loader2 size={12} className="animate-spin" />
                              ) : (
                                <Play size={10} className="fill-white" />
                              )}
                              <span>{msg.is_executing ? "Inserting Records..." : "Confirm & Execute"}</span>
                            </button>
                            <button
                              onClick={() => handleCancelModification(idx)}
                              disabled={msg.is_executing}
                              className="bg-white border border-amber-300 hover:bg-amber-100/50 text-amber-900 px-3.5 py-2 rounded-lg text-xs font-medium cursor-pointer transition disabled:opacity-50"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      )}

                      {/* Results and Visualization Section */}
                      {msg.sql && !msg.canceled && (
                        <div className="border border-[#E2E8F0] rounded-lg bg-white overflow-hidden shadow-xs">
                          {/* Action Toolbar */}
                          <div className="bg-[#F8FAFC] border-b border-[#E2E8F0] px-3 py-2 flex items-center justify-between flex-wrap gap-2">
                            <div className="flex items-center gap-1">
                              {msg.records && msg.records.length > 0 && (
                                <>
                                  <button
                                    onClick={() => {
                                      const updated = [...messages];
                                      updated[idx].activeTab = "table";
                                      setMessages(updated);
                                    }}
                                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition cursor-pointer ${
                                      msg.activeTab === "table"
                                        ? "bg-white text-[#172B4D] border border-[#E2E8F0] shadow-xs"
                                        : "text-[#64748B] hover:text-[#172B4D]"
                                    }`}
                                  >
                                    <Table size={12} className={msg.activeTab === "table" ? "text-[#168C88]" : "text-[#64748B]"} />
                                    <span>Table View</span>
                                  </button>

                                  <button
                                    onClick={() => {
                                      const updated = [...messages];
                                      updated[idx].activeTab = "chart";
                                      if (!updated[idx].chartType) updated[idx].chartType = "bar";
                                      setMessages(updated);
                                    }}
                                    className={`flex items-center gap-1.5 px-2.5 py-1 rounded-md text-[11px] font-medium transition cursor-pointer ${
                                      msg.activeTab === "chart"
                                        ? "bg-white text-[#172B4D] border border-[#E2E8F0] shadow-xs"
                                        : "text-[#64748B] hover:text-[#172B4D]"
                                    }`}
                                  >
                                    <BarChart3 size={12} className={msg.activeTab === "chart" ? "text-[#168C88]" : "text-[#64748B]"} />
                                    <span>Chart View</span>
                                  </button>
                                </>
                              )}
                            </div>

                            <div className="flex items-center gap-1 flex-wrap">
                              <button
                                onClick={() => handleExportPDF(msg)}
                                className="flex items-center gap-1 text-[#64748B] hover:text-[#172B4D] hover:bg-white border border-[#E2E8F0] px-2 py-1 rounded text-[10px] font-medium cursor-pointer transition shadow-xs"
                                title="Export PDF Report"
                              >
                                <Download size={10} className="text-[#168C88]" /> PDF
                              </button>
                              {msg.records && msg.records.length > 0 && (
                                <>
                                  <button
                                    onClick={() => handleExportExcel(msg.records!)}
                                    className="flex items-center gap-1 text-[#64748B] hover:text-[#172B4D] hover:bg-white border border-[#E2E8F0] px-2 py-1 rounded text-[10px] font-medium cursor-pointer transition shadow-xs"
                                    title="Export Excel"
                                  >
                                    <Download size={10} className="text-[#168C88]" /> Excel
                                  </button>
                                  <button
                                    onClick={() => handleExportCSV(msg.records!)}
                                    className="flex items-center gap-1 text-[#64748B] hover:text-[#172B4D] hover:bg-white border border-[#E2E8F0] px-2 py-1 rounded text-[10px] font-medium cursor-pointer transition shadow-xs"
                                    title="Export CSV"
                                  >
                                    <Download size={10} className="text-[#168C88]" /> CSV
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
                                className={`flex items-center gap-1 px-2.5 py-1 rounded text-[10px] font-medium cursor-pointer transition border shadow-xs ${
                                  msg.reportSaved
                                    ? "bg-emerald-50 border-emerald-200 text-emerald-700"
                                    : "bg-white border-[#E2E8F0] text-[#64748B] hover:text-[#172B4D]"
                                }`}
                              >
                                <FolderHeart size={10} className={msg.reportSaved ? "text-emerald-500" : "text-[#168C88]"} />
                                <span>{msg.reportSaved ? "Saved" : "Save Report"}</span>
                              </button>
                            </div>
                          </div>

                          {/* Inline Save Report Input */}
                          {saveReportIdx === idx && (
                            <div className="bg-[#F8FAFC] border-b border-[#E2E8F0] p-2.5 flex items-center justify-between gap-2 text-xs">
                              <input
                                type="text"
                                value={reportTitle}
                                onChange={(e) => setReportTitle(e.target.value)}
                                placeholder="Enter report title..."
                                className="flex-1 bg-white border border-[#E2E8F0] rounded px-2.5 py-1 text-xs text-[#172B4D] focus:outline-none focus:border-[#168C88]"
                              />
                              <div className="flex gap-1.5">
                                <button
                                  onClick={() => handleSaveAsReport(idx, msg)}
                                  disabled={savingReport || !reportTitle.trim()}
                                  className="bg-[#168C88] hover:bg-[#137774] text-white px-2.5 py-1 rounded text-xs font-medium cursor-pointer disabled:opacity-50 flex items-center gap-1 shadow-xs"
                                >
                                  {savingReport && <Loader2 size={11} className="animate-spin" />}
                                  <span>Save</span>
                                </button>
                                <button
                                  onClick={() => {
                                    setSaveReportIdx(null);
                                    setReportTitle("");
                                  }}
                                  disabled={savingReport}
                                  className="bg-white border border-[#E2E8F0] hover:bg-[#F1F5F9] px-2.5 py-1 rounded text-xs text-[#64748B] cursor-pointer"
                                >
                                  Cancel
                                </button>
                              </div>
                            </div>
                          )}

                          {/* Table Container */}
                          {msg.activeTab === "table" && msg.records && (
                            <InnerTable records={msg.records} />
                          )}

                          {/* Chart Container */}
                          {msg.activeTab === "chart" && msg.records && (
                            <InnerChart 
                              records={msg.records} 
                              type={msg.chartType || "bar"} 
                              onChangeType={(type) => {
                                const updated = [...messages];
                                updated[idx].chartType = type;
                                setMessages(updated);
                              }} 
                            />
                          )}
                        </div>
                      )}

                      {/* Success / Modification Metrics */}
                      {!msg.requires_confirmation && msg.rows_affected !== undefined && (
                        <div className="pt-2.5 border-t border-[#E2E8F0] flex items-center justify-between text-[11px] font-medium text-[#64748B]">
                          <div className="flex gap-4">
                            <span>Rows affected: <strong className="text-[#172B4D]">{msg.rows_affected}</strong></span>
                            <span>Execution time: <strong className="text-[#172B4D]">{msg.execution_time_ms} ms</strong></span>
                          </div>
                          
                          {msg.history_id && !msg.is_undone && (
                            <button
                              onClick={() => handleUndo(idx, msg.history_id!)}
                              disabled={msg.is_undoing}
                              className="flex items-center gap-1 text-[#D95D39] hover:text-[#c44f2d] bg-red-50 hover:bg-red-100/60 border border-red-200 px-2 py-0.5 rounded text-xs transition cursor-pointer disabled:opacity-50"
                            >
                              {msg.is_undoing ? (
                                <Loader2 size={11} className="animate-spin" />
                              ) : (
                                <Trash2 size={11} />
                              )}
                              <span>{msg.is_undoing ? "Undoing..." : "Undo Change"}</span>
                            </button>
                          )}

                          {msg.is_undone && (
                            <span className="text-emerald-700 bg-emerald-50 px-2 py-0.5 rounded border border-emerald-200 text-xs">
                              ✓ Undone
                            </span>
                          )}
                        </div>
                      )}
                    </div>
                  </div>
                )}
              </div>
            ))
          )}

          {/* Assistant Loading State */}
          {loading && (
            <div className="flex gap-2.5 items-start">
              <div className="w-7 h-7 rounded-lg bg-[#168C88]/10 border border-[#168C88]/20 text-[#168C88] flex items-center justify-center shrink-0 mt-0.5">
                <Sparkles size={14} />
              </div>
              <div className="bg-white border border-[#E2E8F0] rounded-[10px] px-3.5 py-2.5 shadow-xs flex items-center gap-2.5 text-xs text-[#172B4D]">
                <Loader2 size={14} className="animate-spin text-[#168C88]" />
                <LoadingText />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        {/* Query History Sidebar Drawer */}
        {showHistory && (
          <div className="w-64 border-l border-[#E2E8F0] pl-3 flex flex-col h-full shrink-0 overflow-hidden bg-white">
            <div className="flex justify-between items-center pb-2.5 border-b border-[#E2E8F0] mb-2.5">
              <span className="text-xs font-semibold text-[#172B4D] flex items-center gap-1.5 uppercase tracking-wide">
                <History size={13} className="text-[#FF5722]" /> Query History
              </span>
              {historyList.length > 0 && (
                <button
                  onClick={handleClearAllHistory}
                  className="text-[11px] font-bold text-[#FF5722] hover:text-[#d84315] transition cursor-pointer"
                >
                  Clear All
                </button>
              )}
            </div>

            {loadingHistory && historyList.length === 0 ? (
              <div className="flex-1 flex items-center justify-center">
                <Loader2 className="animate-spin text-[#FF5722]" size={20} />
              </div>
            ) : historyList.length === 0 ? (
              <div className="flex-1 flex flex-col items-center justify-center text-center text-[#64748B] p-4">
                <History size={18} className="text-[#94A3B8] mb-1.5" />
                <span className="text-xs font-medium text-[#64748B]">No query logs yet</span>
              </div>
            ) : (
              <div className="flex-1 overflow-y-auto space-y-2 pr-1">
                {historyList.map((item) => (
                  <div
                    key={item.id}
                    onClick={() => handleReopenHistory(item)}
                    className="p-2.5 bg-[#F8FAFC] hover:bg-white border border-[#E2E8F0] hover:border-[#FF5722]/50 rounded-lg cursor-pointer transition text-left relative group shadow-xs"
                    title="Click to reopen query results"
                  >
                    <p className="text-xs font-medium text-[#172B4D] line-clamp-2 pr-4 leading-snug">
                      {item.question}
                    </p>
                    <div className="flex justify-between items-center mt-2 text-[10px] text-[#64748B]">
                      <span>{item.result_count} records</span>
                      <span>{new Date(item.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                    </div>

                    <button
                      onClick={(e) => handleDeleteHistory(e, item.id)}
                      className="absolute top-1.5 right-1.5 p-1 rounded hover:bg-red-50 text-[#94A3B8] hover:text-[#FF5722] opacity-0 group-hover:opacity-100 transition cursor-pointer"
                      title="Delete log"
                    >
                      <Trash2 size={11} />
                    </button>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Input Form - Rounded search bar style from earlier chat box design */}
      <form
        onSubmit={(e) => {
          e.preventDefault();
          askAI();
        }}
        className="border border-[#168C88]/35 hover:border-[#168C88] focus-within:border-[#168C88] focus-within:ring-2 focus-within:ring-[#168C88]/20 rounded-full p-1.5 pl-4 bg-white flex gap-2 items-center transition-all shadow-xs"
      >
        <textarea
          ref={textareaRef}
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              askAI();
            }
          }}
          placeholder="Ask your query..."
          rows={1}
          style={{ border: "none", outline: "none", boxShadow: "none", background: "transparent" }}
          className="chat-input-textarea no-border flex-1 bg-transparent border-0 border-none outline-none focus:outline-none focus:ring-0 resize-none p-0 text-xs text-[#172B4D] placeholder-gray-400 font-medium"
        />

        <button
          type="submit"
          disabled={loading || !question.trim()}
          className="bg-[#168C88] hover:bg-[#137774] text-white w-8 h-8 rounded-full flex items-center justify-center transition duration-200 disabled:opacity-40 disabled:scale-100 hover:scale-105 active:scale-95 cursor-pointer shrink-0 shadow-xs"
          title="Send query"
        >
          <Send size={13} />
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
          <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 text-[#94A3B8]" size={13} />
          <input
            type="text"
            placeholder="Search query results..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setCurrentPage(1);
            }}
            className="w-full bg-[#F8FAFC] border border-[#E2E8F0] rounded-md pl-8 pr-3 py-1.5 text-xs text-[#172B4D] placeholder-[#94A3B8] focus:outline-none focus:border-[#168C88] focus:bg-white font-normal"
          />
        </div>
      )}

      <div className="overflow-x-auto border border-[#E2E8F0] rounded-lg">
        <table className="min-w-full text-xs text-[#172B4D]">
          <thead className="bg-[#F8FAFC] border-b border-[#E2E8F0]">
            <tr>
              {columns.map(c => (
                <th key={c} className="px-3 py-2 font-semibold text-[#64748B] text-left uppercase whitespace-nowrap text-[10px] tracking-wider">
                  {c}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E2E8F0] bg-white">
            {paginated.map((row, rIdx) => (
              <tr key={rIdx} className="hover:bg-[#F8FAFC] transition-colors">
                {columns.map(c => (
                  <td key={c} className="px-3 py-2 text-[#172B4D] font-normal truncate max-w-[180px]">
                    {row[c] === null ? <span className="text-[#94A3B8] italic">null</span> : formatDateValue(row[c])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-xs text-[#64748B]">
        <span>Showing {start + 1} to {Math.min(start + itemsPerPage, filtered.length)} of {filtered.length} entries</span>
        <div className="flex gap-1">
          <button
            onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
            disabled={currentPage === 1}
            className="p-1 rounded hover:bg-[#F1F5F9] disabled:opacity-30 cursor-pointer border border-[#E2E8F0]"
          >
            <ChevronLeft size={13} />
          </button>
          <button
            onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
            disabled={currentPage === totalPages || totalPages === 0}
            className="p-1 rounded hover:bg-[#F1F5F9] disabled:opacity-30 cursor-pointer border border-[#E2E8F0]"
          >
            <ChevronRight size={13} />
          </button>
        </div>
      </div>
    </div>
  );
}

function LoadingText() {
  const [textIndex, setTextIndex] = useState(0);
  const steps = [
    "Understanding dataset...",
    "Generating SQL...",
    "Running analysis...",
    "Creating visualization..."
  ];

  useEffect(() => {
    const interval = setInterval(() => {
      setTextIndex((prev) => (prev + 1) % steps.length);
    }, 2000);
    return () => clearInterval(interval);
  }, [steps.length]);

  return (
    <span className="text-[#64748B] text-xs font-medium">
      {steps[textIndex]}
    </span>
  );
}

// Inner SVG Chart Renderer Component with enterprise styling
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
      <div className="p-4 text-center text-xs text-[#64748B]">
        <Info size={15} className="mx-auto mb-1 text-[#94A3B8]" />
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
      <div className="flex justify-between items-center text-xs font-medium">
        <span className="text-[#172B4D]">
          Visual: <strong className="font-semibold">{valueKey}</strong> by <strong className="font-semibold">{labelKey}</strong> {records.length > 10 && <span className="text-[10px] text-[#64748B] font-normal">(Top 10 shown)</span>}
        </span>
        <div className="flex border border-[#E2E8F0] rounded-md overflow-hidden bg-[#F8FAFC] p-0.5">
          <button
            onClick={() => onChangeType("bar")}
            className={`p-0.5 px-2 text-[10px] font-medium cursor-pointer rounded ${
              type === "bar" ? "bg-white text-[#172B4D] shadow-xs border border-[#E2E8F0]" : "text-[#64748B] hover:text-[#172B4D]"
            }`}
          >
            Bar
          </button>
          <button
            onClick={() => onChangeType("line")}
            className={`p-0.5 px-2 text-[10px] font-medium cursor-pointer rounded ${
              type === "line" ? "bg-white text-[#172B4D] shadow-xs border border-[#E2E8F0]" : "text-[#64748B] hover:text-[#172B4D]"
            }`}
          >
            Line
          </button>
        </div>
      </div>

      <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl p-3 flex justify-center">
        <svg width="100%" height={height} viewBox={`0 0 ${width} ${height}`} className="max-w-[440px]">
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
                  stroke="#E2E8F0"
                  strokeWidth="1"
                  strokeDasharray="3 3"
                />
                <text
                  x={paddingLeft - 8}
                  y={y + 3}
                  textAnchor="end"
                  fill="#64748B"
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
              const barWidth = Math.max(graphWidth / points.length * 0.45, 6);
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
                    rx="3"
                    className="fill-[#168C88] hover:fill-[#137774] transition-colors cursor-pointer"
                  />
                  <title>{`${pt.label}: ${pt.value.toLocaleString()}`}</title>
                  <text
                    x={pt.x}
                    y={height - 15}
                    textAnchor="middle"
                    fill="#64748B"
                    fontSize="8"
                    fontWeight="500"
                    transform={`rotate(-15, ${pt.x}, ${height - 15})`}
                  >
                    {pt.label.length > 8 ? pt.label.slice(0, 7) + ".." : pt.label}
                  </text>
                </g>
              );
            })
          }

          {type === "line" && (
            <g>
              <defs>
                <linearGradient id="tealGradSmall" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#168C88" stopOpacity="0.18" />
                  <stop offset="100%" stopColor="#168C88" stopOpacity="0.0" />
                </linearGradient>
              </defs>
              
              <path
                d={`${points.map((pt, ptIdx) => `${ptIdx === 0 ? "M" : "L"} ${pt.x} ${pt.y}`).join(" ")} L ${points[points.length-1].x} ${paddingTop+graphHeight} L ${points[0].x} ${paddingTop+graphHeight} Z`}
                fill="url(#tealGradSmall)"
              />

              <path
                d={points.map((pt, ptIdx) => `${ptIdx === 0 ? "M" : "L"} ${pt.x} ${pt.y}`).join(" ")}
                fill="none"
                stroke="#168C88"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              />
              
              {points.map((pt, circleIdx) => (
                <g key={circleIdx} className="group">
                  <circle
                    cx={pt.x}
                    cy={pt.y}
                    r="3.5"
                    className="fill-white stroke-[#168C88] stroke-2 hover:fill-[#168C88] transition-colors cursor-pointer"
                  />
                  <title>{`${pt.label}: ${pt.value.toLocaleString()}`}</title>
                  <text
                    x={pt.x}
                    y={height - 15}
                    textAnchor="middle"
                    fill="#64748B"
                    fontSize="8"
                    fontWeight="500"
                    transform={`rotate(-15, ${pt.x}, ${height - 15})`}
                  >
                    {pt.label.length > 8 ? pt.label.slice(0, 7) + ".." : pt.label}
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

export function formatDateValue(val: any): string {
  if (val === null || val === undefined) return "";
  
  if (typeof val === "number" && !Number.isInteger(val)) {
    return val.toFixed(2);
  }
  
  if (typeof val === "string") {
    const num = Number(val);
    if (val.trim() !== "" && !isNaN(num) && val.includes(".") && !Number.isInteger(num)) {
      return num.toFixed(2);
    }
  }

  const s = String(val);
  if (/^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}:\d{2})?/.test(s)) {
    if (s.includes("00:00:00") || s.includes("T00:00:00")) {
      return s.split(/[T ]/)[0];
    }
  }
  return s;
}
