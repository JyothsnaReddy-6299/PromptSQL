import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import axios from 'axios'
import './index.css'
import App from './App.tsx'

// Generate persistent unique anonymous user ID if it doesn't exist
let userId = localStorage.getItem("promptsql_user_id");
if (!userId) {
  userId = "usr_" + Math.random().toString(36).substring(2, 11) + Math.random().toString(36).substring(2, 11);
  localStorage.setItem("promptsql_user_id", userId);
}

// Configure axios interceptor to inject user and table identifiers automatically
axios.interceptors.request.use((config) => {
  const currentUserId = localStorage.getItem("promptsql_user_id");
  if (currentUserId) {
    config.headers["X-User-ID"] = currentUserId;
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

