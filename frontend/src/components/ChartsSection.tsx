export default function ChartsSection() {
  return (

    <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

      {/* Chart 1 */}
      <div className="bg-white rounded-2xl shadow-sm p-6">

        <h2 className="text-lg font-semibold mb-4">
          Sales Distribution
        </h2>

        <div className="
            h-72
            rounded-xl
            bg-slate-100
            flex
            items-center
            justify-center
            text-gray-400
        ">
          Chart Placeholder
        </div>

      </div>


      {/* Chart 2 */}
      <div className="bg-white rounded-2xl shadow-sm p-6">

        <h2 className="text-lg font-semibold mb-4">
          Country Analysis
        </h2>

        <div className="
            h-72
            rounded-xl
            bg-slate-100
            flex
            items-center
            justify-center
            text-gray-400
        ">
          Chart Placeholder
        </div>

      </div>

    </div>

  );
}