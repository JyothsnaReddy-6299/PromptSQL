const API_URL = import.meta.env.VITE_API_URL || "";

// Custom fetch wrapper to automatically inject user session and JWT authorization headers
const originalFetch = window.fetch;
const fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
  const headers = { ...(init?.headers as Record<string, string> || {}) };
  const userId = localStorage.getItem("promptsql_user_id");
  if (userId) {
    headers["X-User-ID"] = userId;
  }
  const token = localStorage.getItem("promptsql_token");
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  try {
    const dataset = JSON.parse(sessionStorage.getItem("dataset") || "{}");
    if (dataset && dataset.table_name) {
      headers["X-Table-Name"] = dataset.table_name;
    }
  } catch (e) {
    // Ignore parsing errors
  }
  const response = await originalFetch(input, {
    ...init,
    headers,
  });
  const requestUrl = typeof input === "string" ? input : (input as any).url || "";
  if (response.status === 401 && !requestUrl.includes("/auth/login")) {
    localStorage.removeItem("promptsql_token");
    localStorage.removeItem("promptsql_user_id");
    localStorage.removeItem("promptsql_username");
    sessionStorage.clear();
    window.location.href = "/login";
  }
  return response;
};



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

export async function getPreview(search?: string, sortCol?: string, sortDir?: string, page: number = 1, limit: number = 100) {
  let url = `${API_URL}/preview?`;
  const params = [];
  if (search) params.push(`search=${encodeURIComponent(search)}`);
  if (sortCol) params.push(`sort_col=${encodeURIComponent(sortCol)}`);
  if (sortDir) params.push(`sort_dir=${encodeURIComponent(sortDir)}`);
  if (page) params.push(`page=${page}`);
  if (limit) params.push(`limit=${limit}`);
  url += params.join("&");
  const response = await fetch(url);
  return response.json();
}

// -------------------------------------------------------------
// DATASET LIBRARY API
// -------------------------------------------------------------
export async function getDatasets() {
  const response = await fetch(`${API_URL}/datasets`);
  if (!response.ok) throw new Error("Failed fetching datasets");
  return response.json();
}

export async function setActiveDataset(tableName: string) {
  const response = await fetch(`${API_URL}/datasets/active`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ table_name: tableName }),
  });
  if (!response.ok) throw new Error("Failed setting active dataset");
  return response.json();
}

export async function deleteDataset(tableName: string) {
  const response = await fetch(`${API_URL}/datasets/${encodeURIComponent(tableName)}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error("Failed deleting dataset");
  return response.json();
}

export async function createTable(tableName: string, columns: { name: string; type: string }[]) {
  const response = await fetch(`${API_URL}/datasets/create`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ table_name: tableName, columns }),
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed creating table");
  }
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

export async function undoHistoryItem(id: number) {
  const response = await fetch(`${API_URL}/api/history/${id}/undo`, {
    method: "POST",
  });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || "Failed to undo database change");
  }
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

// -------------------------------------------------------------
// DML & DDL MODIFICATIONS API
// -------------------------------------------------------------
export async function askModification(question: string) {
  const response = await fetch(`${API_URL}/api/modification/ask`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ question }),
  });
  if (!response.ok) {
    const detail = await response.json();
    throw new Error(detail?.detail || "SQL Generation for modification failed");
  }
  return response.json();
}

export async function executeModification(sql: string, intent: string, tableName: string, question: string) {
  const response = await fetch(`${API_URL}/api/modification/execute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({ sql, intent, table_name: tableName, question }),
  });
  if (!response.ok) throw new Error("Failed executing database modification query");
  return response.json();
}

export async function getAuditLogs() {
  const response = await fetch(`${API_URL}/api/audit`);
  if (!response.ok) throw new Error("Failed fetching audit logs");
  return response.json();
}

export async function deleteAuditLog(logId: number) {
  const response = await fetch(`${API_URL}/api/audit/${logId}`, {
    method: "DELETE",
  });
  if (!response.ok) throw new Error("Failed deleting audit log");
  return response.json();
}

// -------------------------------------------------------------
// DATA CLEANING API
// -------------------------------------------------------------
export async function cleanRemoveDuplicates() {
  const response = await fetch(`${API_URL}/api/clean/remove-duplicates`, {
    method: "POST",
  });
  if (!response.ok) throw new Error("Failed removing duplicates");
  return response.json();
}

export async function cleanImpute(columnName: string, strategy: string, customValue?: string) {
  const response = await fetch(`${API_URL}/api/clean/impute`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      column_name: columnName,
      strategy,
      custom_value: customValue,
    }),
  });
  if (!response.ok) throw new Error("Failed imputing column values");
  return response.json();
}

export async function cleanUpdateCell(columnName: string, newValue: string, rowData: Record<string, any>) {
  const response = await fetch(`${API_URL}/api/clean/update-cell`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      column_name: columnName,
      new_value: newValue,
      row_data: rowData,
    }),
  });
  if (!response.ok) throw new Error("Failed updating cell value");
  return response.json();
}

export async function cleanConvertType(columnName: string, targetType: string) {
  const response = await fetch(`${API_URL}/api/clean/convert-type`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      column_name: columnName,
      target_type: targetType,
    }),
  });
  if (!response.ok) throw new Error("Failed converting column type");
  return response.json();
}

export async function cleanStandardizeText(columnName: string, operation: string) {
  const response = await fetch(`${API_URL}/api/clean/standardize-text`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      column_name: columnName,
      operation,
    }),
  });
  if (!response.ok) throw new Error("Failed standardizing text");
  return response.json();
}

export async function cleanExtractNumbers(columnName: string) {
  const response = await fetch(`${API_URL}/api/clean/extract-numbers`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      column_name: columnName,
    }),
  });
  if (!response.ok) throw new Error("Failed extracting numbers");
  return response.json();
}


export async function detectNumericTextColumns() {
  const response = await fetch(`${API_URL}/api/clean/detect-numeric-text`);
  if (!response.ok) throw new Error("Failed detecting numeric text columns");
  return response.json();
}

export async function cleanExtractAndConvert(columnName: string) {
  const response = await fetch(`${API_URL}/api/clean/extract-and-convert`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ column_name: columnName }),
  });
  if (!response.ok) throw new Error("Failed extract and convert");
  return response.json();
}

export async function locateMissingCells(columnName: string) {
  const response = await fetch(`${API_URL}/api/clean/locate-missing?column_name=${encodeURIComponent(columnName)}`);
  if (!response.ok) throw new Error("Failed to locate missing cells");
  return response.json();
}

export async function login(username: string, password: string) {
  const response = await fetch(`${API_URL}/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Login failed");
  return data;
}

export async function signup(username: string, password: string) {
  const response = await fetch(`${API_URL}/auth/signup`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.detail || "Signup failed");
  return data;
}

export async function downloadRawCSV() {
  const response = await fetch(`${API_URL}/api/export/raw/csv`);
  await triggerBlobDownload(response, "dataset.csv");
}

export async function downloadRawExcel() {
  const response = await fetch(`${API_URL}/api/export/raw/excel`);
  await triggerBlobDownload(response, "dataset.xlsx");
}