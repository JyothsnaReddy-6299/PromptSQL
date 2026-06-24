interface Props {
  fileName?: string;
}

export default function DashboardNavbar({ fileName }: Props) {
  return (
    <div className="bg-white rounded-2xl shadow-sm px-6 py-4 flex items-center justify-between">

      {/* Left side */}
      <div>
        <h1 className="text-2xl font-bold text-gray-800">
          Dashboard
        </h1>

        <p className="text-sm text-gray-500">
          {fileName || "No file uploaded"}
        </p>
      </div>

      {/* Right side (optional simple UI) */}
      <div className="flex items-center gap-3">

        <div className="w-10 h-10 rounded-full bg-blue-100 flex items-center justify-center">
          <span className="text-blue-600 font-semibold">AI</span>
        </div>

      </div>

    </div>
  );
}