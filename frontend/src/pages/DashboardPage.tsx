import DashboardSidebar from "../components/DashboardSidebar";
import DashboardNavbar from "../components/DashboardNavbar";
import KPICards from "../components/KPICards";
import ChartsSection from "../components/ChartsSection";
import AIInsights from "../components/AIInsights";
import ChatBox from "../components/ChatBox";
import { useLocation } from "react-router-dom";

export default function DashboardPage() {

    const location = useLocation();

    const data =
        location.state ||
        JSON.parse(sessionStorage.getItem("dataset") || "{}");

    const fileName = data?.filename || "No file uploaded";
    const rows = data?.rows || 0;
    const columns = data?.columns || 0;
    const missing = data?.missing_values || 0;
    const size = data?.size || "N/A";

    return (
        <div className="flex min-h-screen bg-slate-50">

            <DashboardSidebar />

            <div className="flex-1 p-6">

                <DashboardNavbar fileName={fileName} />

                <div className="mt-6">
                    <KPICards
                        rows={rows}
                        columns={columns}
                        missing={missing}
                        size={size}
                    />
                </div>

                <div className="mt-8">
                    <ChatBox />
                </div>

                <div className="mt-8">
                    <ChartsSection />
                </div>

                <div className="mt-8">
                    <AIInsights />
                </div>

            </div>
        </div>
    );
}