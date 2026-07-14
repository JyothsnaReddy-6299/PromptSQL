import { useState, useEffect } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import DashboardSidebar from "../components/DashboardSidebar";
import DashboardNavbar from "../components/DashboardNavbar";
import KPICards from "../components/KPICards";
import ChatBox from "../components/ChatBox";
import TablePreview from "../components/TablePreview";
import ReportsManager from "../components/ReportsManager";
import AuditManager from "../components/AuditManager";
import DataCleaner from "../components/DataCleaner";
import { getPreview } from "../services/api";

export default function DashboardPage() {
  const location = useLocation();
  const navigate = useNavigate();

  const [activeSection, setActiveSection] = useState("overview");
  const [previewColumns, setPreviewColumns] = useState<string[]>([]);
  const [previewRecords, setPreviewRecords] = useState<Record<string, any>[]>([]);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");
  const [sortCol, setSortCol] = useState("");
  const [sortDir, setSortDir] = useState("ASC");
  const [columnMissing, setColumnMissing] = useState<Record<string, number>>({});

  const datasetMeta =
    location.state ||
    JSON.parse(sessionStorage.getItem("dataset") || "{}");

  const fileName = datasetMeta?.filename || "";
  const rows = datasetMeta?.rows || 0;
  const columnsCount = datasetMeta?.columns || 0;
  const missing = datasetMeta?.missing_values || 0;
  const [detectedTypes, setDetectedTypes] = useState<Record<string, string>>(datasetMeta?.detected_types || {});

  const size = datasetMeta?.size || `${((rows * columnsCount * 12) / 1024).toFixed(1)} KB`;

  const [totalRows, setTotalRows] = useState(rows);
  const [totalCols, setTotalCols] = useState(columnsCount);
  const [totalMissing, setTotalMissing] = useState(missing);

  useEffect(() => {
    if (rows) {
      setTotalRows(rows);
    }
  }, [rows]);

  useEffect(() => {
    if (columnsCount) {
      setTotalCols(columnsCount);
    }
  }, [columnsCount]);

  useEffect(() => {
    if (missing) {
      setTotalMissing(missing);
    }
  }, [missing]);

  useEffect(() => {
    if (!fileName) {
      navigate("/upload");
      return;
    }

    const timer = setTimeout(() => {
      const fetchDatasetPreview = async () => {
        try {
          setLoadingPreview(true);
          const data = await getPreview(searchTerm, sortCol, sortDir);
          if (data.success) {
            setPreviewColumns(data.columns || []);
            setPreviewRecords(data.records || []);
            if (data.columns) {
              setTotalCols(data.columns.length);
            }
            if (typeof data.total_rows === "number") {
              setTotalRows(data.total_rows);
            }
            if (typeof data.total_missing === "number") {
              setTotalMissing(data.total_missing);
            }
            if (data.column_missing) {
              setColumnMissing(data.column_missing);
            }
            if (data.detected_types) {
              setDetectedTypes(data.detected_types);
              const updatedMeta = { 
                ...datasetMeta, 
                detected_types: data.detected_types,
                missing_values: data.total_missing ?? datasetMeta.missing_values,
                rows: data.total_rows ?? datasetMeta.rows
              };
              sessionStorage.setItem("dataset", JSON.stringify(updatedMeta));
            }
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
    }, 250);

    return () => clearTimeout(timer);
  }, [fileName, refreshTrigger, searchTerm, sortCol, sortDir, navigate]);

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
    if (activeSection === "reports" || activeSection === "audit" || activeSection === "cleaner") return;

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
    <div className="flex min-h-screen bg-[#09090B] text-zinc-100">
      {/* Left Sidebar */}
      <DashboardSidebar
        activeSection={activeSection}
        onSectionClick={handleSectionClick}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col overflow-hidden max-h-screen">
        {/* Sticky Navbar at top of content */}
        <DashboardNavbar
          fileName={fileName}
          onRefresh={() => setRefreshTrigger(p => p + 1)}
          isRefreshing={loadingPreview}
        />

        <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {activeSection === "reports" ? (
          <div id="reports" className="scroll-mt-24">
            <ReportsManager />
          </div>
        ) : activeSection === "audit" ? (
          <div id="audit" className="scroll-mt-24">
            <AuditManager />
          </div>
        ) : activeSection === "cleaner" ? (
          <div id="cleaner" className="scroll-mt-24">
            <DataCleaner 
              columns={previewColumns}
              detectedTypes={detectedTypes}
              columnMissing={columnMissing}
              onRefresh={() => setRefreshTrigger((p) => p + 1)}
              loading={loadingPreview}
            />
          </div>
        ) : (
          <>
            {/* Overview Section */}
            <div id="overview" className="scroll-mt-24 space-y-4">
              <KPICards
                rows={totalRows}
                columns={totalCols}
                missing={totalMissing}
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
                searchTerm={searchTerm}
                onSearchChange={setSearchTerm}
                sortCol={sortCol}
                sortDir={sortDir}
                onSortChange={(col, dir) => {
                  setSortCol(col);
                  setSortDir(dir);
                }}
                onRefresh={() => setRefreshTrigger((p) => p + 1)}
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
    </div>
  );
}