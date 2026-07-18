import { useState, useEffect } from "react";
import { 
  ClipboardList, 
  Loader2, 
  Calendar, 
  Terminal, 
  CheckCircle2, 
  XCircle,
  Database,
  Trash2
} from "lucide-react";
import { getAuditLogs, deleteAuditLog } from "../services/api";

export default function AuditManager() {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const loadAuditHistory = async () => {
    try {
      setLoading(true);
      setError("");
      const data = await getAuditLogs();
      setLogs(data);
    } catch (err: any) {
      setError(err.message || "Failed fetching audit history logs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAuditHistory();
  }, []);

  const handleDeleteLog = async (logId: number) => {
    if (!confirm("Are you sure you want to delete this audit log entry?")) return;
    try {
      await deleteAuditLog(logId);
      setLogs((prev) => prev.filter((log) => log.id !== logId));
    } catch (err: any) {
      alert(err.message || "Failed to delete log entry");
    }
  };

  const formatIST = (timestampStr: string) => {
    try {
      const date = new Date(timestampStr);
      return date.toLocaleString("en-IN", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "numeric",
        minute: "numeric",
        second: "numeric",
        hour12: true,
        timeZone: "Asia/Kolkata"
      });
    } catch (e) {
      return timestampStr;
    }
  };

  const getOperationBadgeColor = (op: string) => {
    const o = op.toUpperCase();
    if (o === "INSERT") return "bg-emerald-500/10 text-emerald-400 border-emerald-500/20";
    if (o === "UPDATE") return "bg-amber-500/10 text-amber-400 border-amber-500/20";
    if (o === "DELETE") return "bg-red-500/10 text-red-400 border-red-500/20";
    if (o === "DROP" || o === "TRUNCATE") return "bg-rose-500/15 text-rose-400 border-rose-500/25";
    return "bg-white/[0.04] text-zinc-400 border-white/[0.08]";
  };

  return (
    <div id="audit" className="bg-[#111113] border border-white/[0.06] rounded-2xl p-5 shadow-2xl shadow-black/10">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-base font-bold text-white flex items-center gap-2">
            <ClipboardList className="text-terracotta-500" size={18} />
            <span>Database Audit History Log</span>
          </h2>
          <p className="text-zinc-400 text-[10px] mt-0.5 font-semibold">
            Chronological audit log of all database schema DDL & data modification DML operations
          </p>
        </div>
        <button
          onClick={loadAuditHistory}
          className="text-xs font-bold text-terracotta-500 hover:text-terracotta-600 transition cursor-pointer"
        >
          Refresh Logs
        </button>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <Loader2 className="animate-spin text-terracotta-500" size={24} />
        </div>
      ) : error ? (
        <div className="h-32 flex items-center justify-center border border-dashed border-red-200 bg-red-50/20 text-red-800 rounded-xl p-4 text-xs font-bold">
          {error}
        </div>
      ) : logs.length === 0 ? (
        <div className="h-64 flex flex-col items-center justify-center text-zinc-500 border border-dashed border-white/[0.08] rounded-xl p-6">
          <ClipboardList className="text-zinc-600 mb-1.5" size={32} />
          <p className="text-xs font-bold text-zinc-300">Audit log is empty.</p>
          <p className="text-[10px] text-zinc-500 mt-0.5">Run data insertion, update, delete, or structure changes to view histories.</p>
        </div>
      ) : (
        <div className="overflow-x-auto border border-white/[0.06] rounded-xl max-h-[500px]">
          <table className="min-w-full border-collapse text-left text-xs text-zinc-350">
            <thead className="bg-[#18181B] sticky top-0 border-b border-white/[0.06] z-10 font-bold text-[9px] uppercase text-zinc-400 tracking-wider">
              <tr>
                <th className="px-4 py-3">Timestamp (IST)</th>
                <th className="px-4 py-3">Operation</th>
                <th className="px-4 py-3">Target Table</th>
                <th className="px-4 py-3">SQL statement</th>
                <th className="px-4 py-3 text-center">Affected</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Diagnostics</th>
                <th className="px-4 py-3 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/[0.04] bg-[#111113] font-semibold">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-white/[0.02] transition">
                  {/* Timestamp */}
                  <td className="px-4 py-3.5 whitespace-nowrap text-zinc-400 text-[10px]">
                    <div className="flex items-center gap-1.5 font-bold">
                      <Calendar size={12} className="text-zinc-500" />
                      <span>{formatIST(log.timestamp)}</span>
                    </div>
                  </td>
                  
                  {/* Operation */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <span className={`px-2 py-0.5 text-[9px] font-bold rounded-full border ${getOperationBadgeColor(log.operation)}`}>
                      {log.operation}
                    </span>
                  </td>

                  {/* Table Name */}
                  <td className="px-4 py-3.5 whitespace-nowrap text-white font-bold">
                    <div className="flex items-center gap-1">
                      <Database size={11} className="text-zinc-500" />
                      <span>{log.table_name.split("_usr_")[0]}</span>
                    </div>
                  </td>

                  {/* Executed SQL */}
                  <td className="px-4 py-3.5 max-w-sm truncate font-mono text-[10.5px] text-indigo-400" title={log.generated_sql}>
                    <div className="flex items-center gap-1.5">
                      <Terminal size={11} className="text-terracotta-400" />
                      <span className="truncate">{log.generated_sql}</span>
                    </div>
                  </td>

                  {/* Rows Affected */}
                  <td className="px-4 py-3.5 text-center text-zinc-200 font-bold whitespace-nowrap">
                    {log.rows_affected}
                  </td>

                  {/* Status */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    {log.status === "SUCCESS" ? (
                      <span className="flex items-center gap-1 text-emerald-400 text-[10px] font-bold">
                        <CheckCircle2 size={12} />
                        <span>Success</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-red-400 text-[10px] font-bold">
                        <XCircle size={12} />
                        <span>Failed</span>
                      </span>
                    )}
                  </td>

                  {/* Diagnostic / Error Message */}
                  <td className="px-4 py-3.5 max-w-xs truncate text-[10px] font-mono text-red-450" title={log.error_message || ""}>
                    {log.error_message || <span className="text-zinc-600 italic">none</span>}
                  </td>

                  {/* Actions (Delete) */}
                  <td className="px-4 py-3.5 whitespace-nowrap text-right">
                    <button
                      onClick={() => handleDeleteLog(log.id)}
                      className="p-1.5 text-zinc-500 hover:text-red-400 hover:bg-red-500/10 rounded-lg transition cursor-pointer"
                      title="Delete log entry"
                    >
                      <Trash2 size={13} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
