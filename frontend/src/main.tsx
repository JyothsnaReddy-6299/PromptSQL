import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import axios from 'axios'
import './index.css'
import App from './App.tsx'

axios.defaults.baseURL = import.meta.env.VITE_API_URL || "";

// Configure axios interceptor to inject user, table, and JWT auth token automatically
axios.interceptors.request.use((config) => {
  const currentUserId = localStorage.getItem("promptsql_user_id");
  if (currentUserId) {
    config.headers["X-User-ID"] = currentUserId;
  }
  const token = localStorage.getItem("promptsql_token");
  if (token) {
    config.headers["Authorization"] = `Bearer ${token}`;
  }
  try {
    const dataset = JSON.parse(sessionStorage.getItem("dataset") || "{}");
    if (dataset && dataset.table_name) {
      config.headers["X-Table-Name"] = dataset.table_name;
    }
  } catch (e) {
    // Ignore parsing errors
  }
  return config;
});

// Auto-redirect to login page if session is expired (401 Unauthorized)
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      localStorage.removeItem("promptsql_token");
      localStorage.removeItem("promptsql_user_id");
      localStorage.removeItem("promptsql_username");
      sessionStorage.clear();
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

