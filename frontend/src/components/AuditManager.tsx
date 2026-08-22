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
    if (o === "INSERT") return "bg-emerald-50 text-emerald-700 border-emerald-200";
    if (o === "UPDATE") return "bg-amber-50 text-amber-700 border-amber-200";
    if (o === "DELETE") return "bg-red-50 text-red-700 border-red-200";
    if (o === "DROP" || o === "TRUNCATE") return "bg-rose-50 text-rose-700 border-rose-200";
    return "bg-[#F7F2EC] text-[#6F6A67] border-[#E8DED3]";
  };

  return (
    <div id="audit" className="bg-[#FFFDFC] border border-[#E8DED3] rounded-2xl p-5 shadow-xl shadow-[#5A2F59]/5">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-base font-bold text-[#241C20] flex items-center gap-2">
            <ClipboardList className="text-[#5A2F59]" size={18} />
            <span>Database Audit History Log</span>
          </h2>
          <p className="text-[#6F6A67] text-[10px] mt-0.5 font-semibold">
            Chronological audit log of all database schema DDL & data modification DML operations
          </p>
        </div>
        <button
          onClick={loadAuditHistory}
          className="text-xs font-bold text-[#5A2F59] hover:text-[#4A2549] transition cursor-pointer"
        >
          Refresh Logs
        </button>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <Loader2 className="animate-spin text-[#5A2F59]" size={24} />
        </div>
      ) : error ? (
        <div className="h-32 flex items-center justify-center border border-dashed border-red-200 bg-red-50/20 text-red-800 rounded-xl p-4 text-xs font-bold">
          {error}
        </div>
      ) : logs.length === 0 ? (
        <div className="h-64 flex flex-col items-center justify-center text-[#6F6A67] border border-dashed border-[#E8DED3] rounded-xl p-6">
          <ClipboardList className="text-[#6F6A67] mb-1.5" size={32} />
          <p className="text-xs font-bold text-[#241C20]">Audit log is empty.</p>
          <p className="text-[10px] text-[#6F6A67] mt-0.5">Run data insertion, update, delete, or structure changes to view histories.</p>
        </div>
      ) : (
        <div className="overflow-x-auto border border-[#E8DED3] rounded-xl max-h-[500px]">
          <table className="min-w-full border-collapse text-left text-xs text-[#241C20]">
            <thead className="bg-[#F7F2EC] sticky top-0 border-b border-[#E8DED3] z-10 font-bold text-[9px] uppercase text-[#6F6A67] tracking-wider">
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
            <tbody className="divide-y divide-[#E8DED3] bg-[#FFFDFC] font-semibold">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-[#5A2F59]/5 transition">
                  {/* Timestamp */}
                  <td className="px-4 py-3.5 whitespace-nowrap text-[#6F6A67] text-[10px]">
                    <div className="flex items-center gap-1.5 font-bold">
                      <Calendar size={12} className="text-[#6F6A67]" />
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
                  <td className="px-4 py-3.5 whitespace-nowrap text-[#241C20] font-bold">
                    <div className="flex items-center gap-1">
                      <Database size={11} className="text-[#6F6A67]" />
                      <span>{log.table_name.split("_usr_")[0]}</span>
                    </div>
                  </td>

                  {/* Executed SQL */}
                  <td className="px-4 py-3.5 max-w-sm truncate font-mono text-[10.5px] text-[#5A2F59]" title={log.generated_sql}>
                    <div className="flex items-center gap-1.5">
                      <Terminal size={11} className="text-[#6F6A67]" />
                      <span className="truncate">{log.generated_sql}</span>
                    </div>
                  </td>

                  {/* Rows Affected */}
                  <td className="px-4 py-3.5 text-center text-[#241C20] font-bold whitespace-nowrap">
                    {log.rows_affected}
                  </td>

                  {/* Status */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    {log.status === "SUCCESS" ? (
                      <span className="flex items-center gap-1 text-emerald-700 text-[10px] font-bold">
                        <CheckCircle2 size={12} />
                        <span>Success</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-rose-700 text-[10px] font-bold">
                        <XCircle size={12} />
                        <span>Failed</span>
                      </span>
                    )}
                  </td>

                  {/* Diagnostic / Error Message */}
                  <td className="px-4 py-3.5 max-w-xs truncate text-[10px] font-mono text-rose-700" title={log.error_message || ""}>
                    {log.error_message || <span className="text-[#6F6A67] italic font-normal">none</span>}
                  </td>

                  {/* Actions (Delete) */}
                  <td className="px-4 py-3.5 whitespace-nowrap text-right">
                    <button
                      onClick={() => handleDeleteLog(log.id)}
                      className="p-1.5 text-[#6F6A67] hover:text-red-650 hover:bg-red-50 rounded-lg transition cursor-pointer"
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
