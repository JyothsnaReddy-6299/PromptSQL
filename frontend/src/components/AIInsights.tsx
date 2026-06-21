import { Brain } from "lucide-react";

export default function AIInsights() {
  return (
    <div className="bg-white rounded-2xl shadow-sm p-6">

      <div className="flex items-center gap-3 mb-6">
        <Brain className="text-blue-600" size={28} />

        <h2 className="text-xl font-semibold">
          AI Insights
        </h2>
      </div>


      <div className="space-y-4">

        <div className="bg-blue-50 rounded-xl p-4">
          Revenue increased by 12% compared to last month.
        </div>


        <div className="bg-blue-50 rounded-xl p-4">
          Missing values detected in the Age column.
        </div>


        <div className="bg-blue-50 rounded-xl p-4">
          Electronics is the top-performing category.
        </div>

      </div>


      <button
        className="
        mt-6
        bg-blue-600
        text-white
        px-5
        py-3
        rounded-xl
        hover:bg-blue-700
        transition
      "
      >
        Generate Insights
      </button>

    </div>
  );
}