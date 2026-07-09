import { useState, useEffect } from "react";
import { 
  ClipboardList, 
  Loader2, 
  Calendar, 
  Terminal, 
  CheckCircle2, 
  XCircle,
  Database
} from "lucide-react";
import { getAuditLogs } from "../services/api";

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

  const getOperationBadgeColor = (op: string) => {
    const o = op.toUpperCase();
    if (o === "INSERT") return "bg-emerald-50 text-emerald-700 border-emerald-200";
    if (o === "UPDATE") return "bg-amber-50 text-amber-700 border-amber-200";
    if (o === "DELETE") return "bg-red-50 text-red-700 border-red-200";
    if (o === "DROP" || o === "TRUNCATE") return "bg-rose-100 text-rose-800 border-rose-300";
    return "bg-slate-50 text-slate-700 border-slate-200";
  };

  return (
    <div id="audit" className="bg-white border border-warmgray-100 rounded-2xl p-4 shadow-sm">
      <div className="flex justify-between items-center mb-4">
        <div>
          <h2 className="text-base font-bold text-warmgray-900 flex items-center gap-2">
            <ClipboardList className="text-terracotta-500" size={18} />
            <span>Database Audit History Log</span>
          </h2>
          <p className="text-warmgray-500 text-[10px] mt-0.5 font-semibold">
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
        <div className="h-64 flex flex-col items-center justify-center text-warmgray-400 border border-dashed border-warmgray-100 rounded-xl p-6">
          <ClipboardList className="text-warmgray-300 mb-1.5" size={32} />
          <p className="text-xs font-bold text-warmgray-850">Audit log is empty.</p>
          <p className="text-[10px] text-warmgray-450 mt-0.5">Run data insertion, update, delete, or structure changes to view histories.</p>
        </div>
      ) : (
        <div className="overflow-x-auto border border-warmgray-100 rounded-xl max-h-[500px]">
          <table className="min-w-full border-collapse text-left text-xs text-warmgray-850">
            <thead className="bg-warmgray-50 sticky top-0 border-b border-warmgray-100 z-10 font-bold text-[9px] uppercase text-warmgray-500 tracking-wider">
              <tr>
                <th className="px-4 py-3">Timestamp</th>
                <th className="px-4 py-3">Operation</th>
                <th className="px-4 py-3">Target Table</th>
                <th className="px-4 py-3">SQL statement</th>
                <th className="px-4 py-3 text-center">Affected</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Diagnostics</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-warmgray-100 bg-white font-semibold">
              {logs.map((log) => (
                <tr key={log.id} className="hover:bg-warmgray-50/30 transition">
                  {/* Timestamp */}
                  <td className="px-4 py-3.5 whitespace-nowrap text-warmgray-500 text-[10px]">
                    <div className="flex items-center gap-1.5">
                      <Calendar size={12} className="text-warmgray-400" />
                      <span>{new Date(log.timestamp).toLocaleString()}</span>
                    </div>
                  </td>
                  
                  {/* Operation */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    <span className={`px-2 py-0.5 text-[9px] font-bold rounded-full border ${getOperationBadgeColor(log.operation)}`}>
                      {log.operation}
                    </span>
                  </td>

                  {/* Table Name */}
                  <td className="px-4 py-3.5 whitespace-nowrap text-warmgray-900 font-bold">
                    <div className="flex items-center gap-1">
                      <Database size={11} className="text-warmgray-450" />
                      <span>{log.table_name}</span>
                    </div>
                  </td>

                  {/* Executed SQL */}
                  <td className="px-4 py-3.5 max-w-sm truncate font-mono text-[10.5px] text-warmgray-900" title={log.generated_sql}>
                    <div className="flex items-center gap-1.5">
                      <Terminal size={11} className="text-terracotta-400" />
                      <span className="truncate">{log.generated_sql}</span>
                    </div>
                  </td>

                  {/* Rows Affected */}
                  <td className="px-4 py-3.5 text-center text-warmgray-900 font-bold whitespace-nowrap">
                    {log.rows_affected}
                  </td>

                  {/* Status */}
                  <td className="px-4 py-3.5 whitespace-nowrap">
                    {log.status === "SUCCESS" ? (
                      <span className="flex items-center gap-1 text-emerald-600 text-[10px] font-bold">
                        <CheckCircle2 size={12} />
                        <span>Success</span>
                      </span>
                    ) : (
                      <span className="flex items-center gap-1 text-red-600 text-[10px] font-bold">
                        <XCircle size={12} />
                        <span>Failed</span>
                      </span>
                    )}
                  </td>

                  {/* Diagnostic / Error Message */}
                  <td className="px-4 py-3.5 max-w-xs truncate text-[10px] font-mono text-red-500" title={log.error_message || ""}>
                    {log.error_message || <span className="text-warmgray-400 italic">none</span>}
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
