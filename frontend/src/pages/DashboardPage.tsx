import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import DashboardSidebar from "../components/DashboardSidebar";
import DashboardNavbar from "../components/DashboardNavbar";
import KPICards from "../components/KPICards";
import ChatBox from "../components/ChatBox";
import TablePreview from "../components/TablePreview";
import ReportsManager from "../components/ReportsManager";
import AuditManager from "../components/AuditManager";
import { getPreview } from "../services/api";

export default function DashboardPage() {
  const location = useLocation();
  const navigate = useNavigate();

  const [activeSection, setActiveSection] = useState("overview");
  const [previewColumns, setPreviewColumns] = useState<string[]>([]);
  const [previewRecords, setPreviewRecords] = useState<Record<string, any>[]>([]);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const datasetMeta =
    location.state ||
    JSON.parse(sessionStorage.getItem("dataset") || "{}");

  const fileName = datasetMeta?.filename || "";
  const rows = datasetMeta?.rows || 0;
  const columnsCount = datasetMeta?.columns || 0;
  const missing = datasetMeta?.missing_values || 0;
  const detectedTypes = datasetMeta?.detected_types || {};

  const size = datasetMeta?.size || `${((rows * columnsCount * 12) / 1024).toFixed(1)} KB`;

  useEffect(() => {
    if (!fileName) {
      navigate("/upload");
      return;
    }

    const fetchDatasetPreview = async () => {
      try {
        setLoadingPreview(true);
        const data = await getPreview();
        if (data.success) {
          setPreviewColumns(data.columns || []);
          setPreviewRecords(data.records || []);
        } else {
          console.error("Preview load failure:", data.error);
        }
      } catch (e) {
        console.error("Failed fetching preview:", e);
      } finally {
        setLoadingPreview(false);
      }
    };

    fetchDatasetPreview();
  }, [fileName, refreshTrigger, navigate]);

  useEffect(() => {
    const handleModified = () => {
      setRefreshTrigger((p) => p + 1);
    };
    window.addEventListener("dataset-modified", handleModified);
    return () => {
      window.removeEventListener("dataset-modified", handleModified);
    };
  }, []);

  useEffect(() => {
    if (activeSection === "reports" || activeSection === "audit") return;

    const sections = ["overview", "preview", "chat"];
    
    const observerOptions = {
      root: null,
      rootMargin: "-15% 0px -75% 0px",
      threshold: 0
    };

    const observerCallback = (entries: IntersectionObserverEntry[]) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          setActiveSection(entry.target.id);
        }
      });
    };

    const observer = new IntersectionObserver(observerCallback, observerOptions);

    sections.forEach((id) => {
      const element = document.getElementById(id);
      if (element) observer.observe(element);
    });

    return () => {
      sections.forEach((id) => {
        const element = document.getElementById(id);
        if (element) observer.unobserve(element);
      });
    };
  }, [previewRecords, activeSection]);

  const handleSectionClick = (sectionId: string) => {
    setActiveSection(sectionId);
    if (sectionId !== "reports" && sectionId !== "audit") {
      setTimeout(() => {
        const element = document.getElementById(sectionId);
        if (element) {
          element.scrollIntoView({
            behavior: "smooth",
            block: "start"
          });
        }
      }, 50);
    }
  };

  return (
    <div className="flex min-h-screen bg-warmgray-50 text-warmgray-900">
      {/* Left Sidebar */}
      <DashboardSidebar 
        activeSection={activeSection} 
        onSectionClick={handleSectionClick} 
      />

      {/* Main Content Area - Reduced Padding & Spacing */}
      <div className="flex-1 p-4 md:p-6 space-y-5 overflow-y-auto max-h-screen">
        {/* Navbar */}
        <DashboardNavbar 
          fileName={fileName} 
          onRefresh={() => setRefreshTrigger(p => p + 1)}
          isRefreshing={loadingPreview}
        />

        {activeSection === "reports" ? (
          <div id="reports" className="scroll-mt-24">
            <ReportsManager />
          </div>
        ) : activeSection === "audit" ? (
          <div id="audit" className="scroll-mt-24">
            <AuditManager />
          </div>
        ) : (
          <>
            {/* Overview Section */}
            <div id="overview" className="scroll-mt-24 space-y-4">
              <KPICards
                rows={rows}
                columns={columnsCount}
                missing={missing}
                size={size}
                detectedTypes={detectedTypes}
              />
            </div>

            {/* Raw Dataset Preview Table */}
            <div id="preview" className="scroll-mt-24">
              <TablePreview
                columns={previewColumns}
                records={previewRecords}
                loading={loadingPreview}
              />
            </div>

            {/* Chat box assistant */}
            <div id="chat" className="scroll-mt-24">
              <ChatBox />
            </div>
          </>
        )}
      </div>
    </div>
  );
}