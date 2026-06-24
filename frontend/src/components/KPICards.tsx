interface Props {
  rows?: number;
  columns?: number;
  missing?: number;
  size?: string;
}

export default function KPICards({
  rows = 0,
  columns = 0,
  missing = 0,
  size = "N/A"
}: Props) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">

      {/* Rows */}
      <div className="bg-white rounded-2xl shadow-sm p-6 hover:shadow-md transition">
        <p className="text-gray-500">Rows</p>
        <h2 className="text-3xl font-bold text-gray-800 mt-2">
          {rows}
        </h2>
      </div>

      {/* Columns */}
      <div className="bg-white rounded-2xl shadow-sm p-6 hover:shadow-md transition">
        <p className="text-gray-500">Columns</p>
        <h2 className="text-3xl font-bold text-gray-800 mt-2">
          {columns}
        </h2>
      </div>

      {/* Missing Values */}
      <div className="bg-white rounded-2xl shadow-sm p-6 hover:shadow-md transition">
        <p className="text-gray-500">Missing Values</p>
        <h2 className="text-3xl font-bold text-gray-800 mt-2">
          {missing}
        </h2>
      </div>

      {/* Size */}
      <div className="bg-white rounded-2xl shadow-sm p-6 hover:shadow-md transition">
        <p className="text-gray-500">Dataset Size</p>
        <h2 className="text-3xl font-bold text-gray-800 mt-2">
          {size}
        </h2>
      </div>

    </div>
  );
}