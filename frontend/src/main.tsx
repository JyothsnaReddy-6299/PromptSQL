import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import axios from 'axios'
import './index.css'
import App from './App.tsx'

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

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

