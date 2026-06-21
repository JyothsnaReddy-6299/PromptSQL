import DashboardSidebar from "../components/DashboardSidebar";
import DashboardNavbar from "../components/DashboardNavbar";
import KPICards from "../components/KPICards";
import ChartsSection from "../components/ChartsSection";
import AIInsights from "../components/AIInsights";
import ChatBox from "../components/chatBox";

export default function DashboardPage() {
  return (
    <div className="flex min-h-screen bg-slate-50">

      <DashboardSidebar />

      <div className="flex-1 p-6">

        <DashboardNavbar />

<div className="mt-6">
    <KPICards />
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