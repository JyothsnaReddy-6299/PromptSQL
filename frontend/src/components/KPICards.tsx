import { Database, Columns, AlertCircle, HardDrive } from "lucide-react";

const cards = [
  {
    title: "Rows",
    value: "15,000",
    icon: Database,
  },
  {
    title: "Columns",
    value: "25",
    icon: Columns,
  },
  {
    title: "Missing Values",
    value: "125",
    icon: AlertCircle,
  },
  {
    title: "Dataset Size",
    value: "3.2 MB",
    icon: HardDrive,
  },
];

export default function KPICards() {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-6">
      {cards.map((card) => {
        const Icon = card.icon;

        return (
          <div
            key={card.title}
            className="bg-white rounded-2xl shadow-sm p-6 hover:shadow-md transition"
          >
            <div className="flex justify-between items-center">

              <div>
                <p className="text-sm text-gray-500">
                  {card.title}
                </p>

                <h2 className="text-3xl font-bold text-gray-800 mt-2">
                  {card.value}
                </h2>
              </div>

              <div className="bg-blue-100 p-3 rounded-xl">
                <Icon size={24} className="text-blue-600" />
              </div>

            </div>
          </div>
        );
      })}
    </div>
  );
}