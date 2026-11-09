import { useState, useEffect, useRef } from "react";
import { useNavigate } from "react-router-dom";
import DashboardSidebar from "../components/DashboardSidebar";
import DashboardNavbar from "../components/DashboardNavbar";
import KPICards from "../components/KPICards";
import ChatBox from "../components/ChatBox";
import TablePreview from "../components/TablePreview";
import ReportsManager from "../components/ReportsManager";
import AuditManager from "../components/AuditManager";
import DataCleaner from "../components/DataCleaner";
import { getPreview } from "../services/api";
import QueryWorkspaceModal from "../components/QueryWorkspaceModal";

export default function DashboardPage() {
  const navigate = useNavigate();

  const [activeSection, setActiveSection] = useState("overview");
  const contentScrollRef = useRef<HTMLDivElement>(null);
  const isManualNavRef = useRef(false);

  const [previewColumns, setPreviewColumns] = useState<string[]>([]);
  const [previewRecords, setPreviewRecords] = useState<Record<string, any>[]>([]);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0);
  const [searchTerm, setSearchTerm] = useState("");
  const [sortCol, setSortCol] = useState("");
  const [sortDir, setSortDir] = useState("ASC");
  const [columnMissing, setColumnMissing] = useState<Record<string, number>>({});
  const [columnStats, setColumnStats] = useState<Record<string, any>>({});
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [modalView, setModalView] = useState<"options" | "create">("options");

  // Lifted Chat Assistant states to preserve conversation across sidebar section switches
  const [chatMessages, setChatMessages] = useState<any[]>([
    {
      sender: "ai",
      text: "Hello! I am your AI Analytics Assistant. Ask me anything about your uploaded dataset in plain English. I'll translate your question into optimized SQL, fetch the results, and explain the trends for you!"
    }
  ]);
  const [chatQuestion, setChatQuestion] = useState("");

  const datasetMeta = JSON.parse(sessionStorage.getItem("dataset") || "{}");

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
            if (data.column_stats) {
              setColumnStats(data.column_stats);
            }
            if (data.detected_types) {
              setDetectedTypes(data.detected_types);
              const updatedMeta = { 
                ...datasetMeta, 
                detected_types: data.detected_types,
                columns: data.columns ? data.columns.length : datasetMeta.columns,
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

  // Clean chat log only when active dataset switches
  useEffect(() => {
    setChatMessages([
      {
        sender: "ai",
        text: "Hello! I am your AI Analytics Assistant. Ask me anything about your uploaded dataset in plain English. I'll translate your question into optimized SQL, fetch the results, and explain the trends for you!"
      }
    ]);
    setChatQuestion("");
  }, [fileName]);

  useEffect(() => {
    const handleModified = () => {
      setRefreshTrigger((p) => p + 1);
    };
    window.addEventListener("dataset-modified", handleModified);
    return () => {
      window.removeEventListener("dataset-modified", handleModified);
    };
  }, []);

  // Precise scroll spy that accurately tracks which section is currently active
  useEffect(() => {
    const container = contentScrollRef.current;
    if (!container) return;

    const handleScroll = () => {
      if (isManualNavRef.current) return;
      if (activeSection === "reports" || activeSection === "audit" || activeSection === "cleaner") return;

      const scrollPos = container.scrollTop + 140;

      const chatEl = document.getElementById("chat");
      const previewEl = document.getElementById("preview");
      const overviewEl = document.getElementById("overview");

      if (chatEl && scrollPos >= chatEl.offsetTop) {
        setActiveSection("chat");
      } else if (previewEl && scrollPos >= previewEl.offsetTop) {
        setActiveSection("preview");
      } else if (overviewEl) {
        setActiveSection("overview");
      }
    };

    container.addEventListener("scroll", handleScroll, { passive: true });
    return () => container.removeEventListener("scroll", handleScroll);
  }, [activeSection]);

  const handleSectionClick = (sectionId: string) => {
    setActiveSection(sectionId);
    if (sectionId === "reports" || sectionId === "audit" || sectionId === "cleaner") {
      return;
    }

    isManualNavRef.current = true;
    setTimeout(() => {
      const element = document.getElementById(sectionId);
      const container = contentScrollRef.current;
      if (element && container) {
        const elementTop = element.offsetTop;
        container.scrollTo({
          top: Math.max(0, elementTop - 16),
          behavior: "smooth"
        });
      }
    }, 10);

    // Release lock once smooth scrolling completes
    setTimeout(() => {
      isManualNavRef.current = false;
    }, 800);
  };

  return (
    <div className="flex min-h-screen bg-[#F5F5F5] text-[#303841]">
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
          onUploadClick={() => navigate("/upload")}
          onCreateTableClick={() => { setModalView("create"); setIsModalOpen(true); }}
        />

        {/* Content container - reduced padding to eliminate zoomed look */}
        <div ref={contentScrollRef} className="flex-1 overflow-y-auto p-4 sm:p-5 space-y-4 bg-[#F5F5F5]">
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
              columnStats={columnStats}
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
                totalRows={totalRows}
              />
            </div>

            {/* Chat box assistant */}
            <div id="chat" className="scroll-mt-24">
              <ChatBox 
                messages={chatMessages}
                setMessages={setChatMessages}
                question={chatQuestion}
                setQuestion={setChatQuestion}
              />
            </div>
          </>
        )}
        </div>
      </div>

      {isModalOpen && (
        <QueryWorkspaceModal
          onClose={() => setIsModalOpen(false)}
          initialView={modalView}
        />
      )}
    </div>
  );
}
