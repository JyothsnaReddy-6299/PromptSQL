import { useState } from "react";
import axios from "axios";

export default function ChatBox() {

  const [question, setQuestion] = useState("");
  const [summary, setSummary] = useState("");
  const [sql, setSql] = useState("");
  const [records, setRecords] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const askAI = async () => {

    if (!question.trim()) {
      setError("Please enter a question");
      return;
    }

    setLoading(true);
    setError("");

    try {
      const response = await axios.post(
        "http://127.0.0.1:8000/ask",
        {
          question,
          table_name: "data"
        }
      );

      const data = response.data;

      // backend error handling
      if (data.error) {
        setError(data.error);
        setSummary("");
        setSql("");
        setRecords([]);
        return;
      }

      setSummary(data.summary || "");
      setSql(data.sql || "");
      setRecords(data.result || []);

    } catch (err: any) {
      setError(err.message || "Something went wrong");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-white p-6 rounded-3xl shadow">

      <h2 className="text-xl font-bold mb-4">
        Ask AI
      </h2>

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask anything about your dataset..."
        className="w-full border rounded-xl p-3 h-32"
      />

      <button
        onClick={askAI}
        className="mt-4 bg-blue-600 text-white px-5 py-2 rounded-xl"
        disabled={loading}
      >
        {loading ? "Thinking..." : "Ask"}
      </button>

      {/* ERROR */}
      {error && (
        <div className="mt-4 text-red-600 font-medium">
          {error}
        </div>
      )}

      {/* SUMMARY */}
      {summary && (
        <div className="mt-6">
          <h3 className="font-semibold text-lg">AI Response</h3>
          <p className="bg-slate-100 p-4 rounded-xl mt-2">
            {summary}
          </p>
        </div>
      )}

      {/* SQL */}
      {sql && (
        <div className="mt-6">
          <h3 className="font-semibold">Generated SQL</h3>
          <div className="bg-slate-100 p-4 rounded-xl mt-2">
            <code>{sql}</code>
          </div>
        </div>
      )}

      {/* RESULT COUNT */}
      {records.length > 0 && (
        <div className="mt-4 text-sm text-gray-600">
          Total Records: {records.length}
        </div>
      )}

    </div>
  );
}