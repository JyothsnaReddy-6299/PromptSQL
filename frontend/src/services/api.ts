const API_URL = "";

// Helper to trigger blob file downloads in the browser
async function triggerBlobDownload(response: Response, defaultFilename: string) {
  if (!response.ok) {
    const errText = await response.text();
    throw new Error(errText || "Export failed.");
  }
  const blob = await response.blob();
  const url = window.URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  
  const disposition = response.headers.get("Content-Disposition");
  let filename = defaultFilename;
  if (disposition && disposition.includes("filename=")) {
    const matches = disposition.match(/filename="?([^"]+)"?/);
    if (matches && matches[1]) {
      filename = matches[1];
    }
  }
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  window.URL.revokeObjectURL(url);
}

export async function getHealth() {
  try {
    const response = await fetch(`${API_URL}/health`);
    return response.json();
  } catch (e) {
    return { success: false, error: String(e) };
  }
}

export async function askQuestion(question: string) {
  const response = await fetch(`${API_URL}/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
    }),
  });
  return response.json();
}

export async function getPreview() {
  const response = await fetch(`${API_URL}/preview`);
  return response.json();
}

// -------------------------------------------------------------
// QUERY HISTORY LOGS API
// -------------------------------------------------------------
export async function getHistory() {
  const response = await fetch(`${API_URL}/api/history`);
  if (!response.ok) throw new Error("Failed fetching history");
  return response.json();
}

export async function deleteHistoryItem(id: number) {
  const response = await fetch(`${API_URL}/api/history/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error("Failed deleting history item");
  return response.json();
}

export async function clearHistory() {
  const response = await fetch(`${API_URL}/api/history`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error("Failed clearing history");
  return response.json();
}

// -------------------------------------------------------------
// SAVED REPORTS API
// -------------------------------------------------------------
export async function getReports() {
  const response = await fetch(`${API_URL}/api/reports`);
  if (!response.ok) throw new Error("Failed fetching reports");
  return response.json();
}

export async function getReportDetail(id: number) {
  const response = await fetch(`${API_URL}/api/reports/${id}`);
  if (!response.ok) throw new Error("Failed fetching report details");
  return response.json();
}

export async function createReport(
  title: string,
  tableName: string,
  question: string,
  sql: string,
  summary: string,
  records: any[]
) {
  const response = await fetch(`${API_URL}/api/reports`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      title,
      table_name: tableName,
      question,
      generated_sql: sql,
      summary,
      records,
    }),
  });
  if (!response.ok) throw new Error("Failed saving report");
  return response.json();
}

export async function renameReport(id: number, title: string) {
  const response = await fetch(`${API_URL}/api/reports/${id}`, {
    method: "PUT",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ title }),
  });
  if (!response.ok) throw new Error("Failed renaming report");
  return response.json();
}

export async function deleteReport(id: number) {
  const response = await fetch(`${API_URL}/api/reports/${id}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error("Failed deleting report");
  return response.json();
}

// -------------------------------------------------------------
// ACTIVE EXPORTS DOWNLOAD API
// -------------------------------------------------------------
export async function downloadActivePDF(
  question: string,
  summary: string,
  sql: string,
  records: any[]
) {
  const response = await fetch(`${API_URL}/api/export/pdf`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question, summary, sql, records }),
  });
  await triggerBlobDownload(response, "active_report.pdf");
}

export async function downloadActiveExcel(records: any[]) {
  const response = await fetch(`${API_URL}/api/export/excel`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ records }),
  });
  await triggerBlobDownload(response, "active_results.xlsx");
}

export async function downloadActiveCSV(records: any[]) {
  const response = await fetch(`${API_URL}/api/export/csv`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ records }),
  });
  await triggerBlobDownload(response, "active_results.csv");
}

// -------------------------------------------------------------
// SAVED REPORT RE-EXPORT API
// -------------------------------------------------------------
export async function downloadReportFile(reportId: number, format: "pdf" | "excel" | "csv", title: string) {
  const response = await fetch(`${API_URL}/api/reports/${reportId}/export/${format}`);
  const extension = format === "excel" ? "xlsx" : format;
  await triggerBlobDownload(response, `${title.replace(/\s+/g, "_")}.${extension}`);
}