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
      setError("Please enter a question.");
      return;
    }

    setLoading(true);
    setError("");

    setSummary("");
    setSql("");
    setRecords([]);

    try {

      const response = await axios.post(
        "http://127.0.0.1:8000/ask",
        {
          question,
          table_name: "ecommerce_sales_dataset" // Change this when using another uploaded table
        }
      );

      const data = response.data;

      if (data.error) {
        setError(data.error);
        return;
      }

      setSummary(data.summary || "");
      setSql(data.sql || "");
      setRecords(data.result || []);

    }
    catch (err: any) {

      if (err.response) {
        setError(err.response.data.error || "Server Error");
      }
      else {
        setError(err.message);
      }

    }
    finally {
      setLoading(false);
    }
  };

  return (

    <div className="bg-white p-6 rounded-3xl shadow">

      <h2 className="text-2xl font-bold mb-5">
        Ask AI
      </h2>

      <textarea
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask anything about your dataset..."
        className="w-full border rounded-xl p-4 h-32"
      />

      <button
        onClick={askAI}
        disabled={loading}
        className="mt-5 bg-blue-600 hover:bg-blue-700 text-white px-6 py-3 rounded-xl"
      >
        {loading ? "Thinking..." : "Ask"}
      </button>

      {error && (
        <div className="mt-5 bg-red-100 text-red-700 p-3 rounded-xl">
          {error}
        </div>
      )}

      {summary && (
        <div className="mt-8">

          <h3 className="text-xl font-semibold">
            AI Response
          </h3>

          <div className="bg-slate-100 rounded-xl p-4 mt-2 whitespace-pre-wrap">
            {summary}
          </div>

        </div>
      )}

      {sql && (
        <div className="mt-8">

          <h3 className="text-xl font-semibold">
            Generated SQL
          </h3>

          <pre className="bg-gray-100 rounded-xl p-4 mt-2 overflow-x-auto">
            <code>{sql}</code>
          </pre>

        </div>
      )}

      {records.length > 0 && (

        <div className="mt-8">

          <h3 className="text-xl font-semibold">
            Retrieved Records
          </h3>

          <p className="text-gray-600 mt-1">
            Total Records: {records.length}
          </p>

          <div className="overflow-auto mt-4 border rounded-xl max-h-[500px]">

            <table className="min-w-full border-collapse">

              <thead className="sticky top-0 bg-gray-100">

                <tr>

                  {Object.keys(records[0]).map((column) => (

                    <th
                      key={column}
                      className="border p-3 text-left font-semibold"
                    >
                      {column}
                    </th>

                  ))}

                </tr>

              </thead>

              <tbody>

                {records.map((row, index) => (

                  <tr
                    key={index}
                    className="hover:bg-gray-50"
                  >

                    {Object.keys(records[0]).map((column) => (

                      <td
                        key={column}
                        className="border p-3"
                      >
                        {String(row[column])}
                      </td>

                    ))}

                  </tr>

                ))}

              </tbody>

            </table>

          </div>

        </div>

      )}

    </div>

  );

}