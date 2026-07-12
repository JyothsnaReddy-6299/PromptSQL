<div align="center">
  
  # 🔮 PromptSQL: AI-Powered Dataset Assistant
  
  [![FastAPI](https://img.shields.io/badge/FastAPI-005571?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
  [![React](https://img.shields.io/badge/React_19-20232A?style=for-the-badge&logo=react&logoColor=61DAFB)](https://react.dev/)
  [![TypeScript](https://img.shields.io/badge/TypeScript-007ACC?style=for-the-badge&logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
  [![MySQL](https://img.shields.io/badge/MySQL-00000F?style=for-the-badge&logo=mysql&logoColor=white)](https://www.mysql.com/)
  [![Groq Llama 3](https://img.shields.io/badge/Groq_Llama_3-f55a2a?style=for-the-badge&logo=groq&logoColor=white)](https://groq.com/)

  *An enterprise-grade **Natural Language to SQL (NL-to-SQL) analytics console** that bridges the gap between raw datasets and business insights. Upload any CSV or Excel file, and chat with your database directly using natural language. The system automatically creates isolated tables, translates your questions into optimized SQL, executes them safely alongside AI-interpreted summaries.*

  ---

  <br />

  <video src="demo video.mp4" controls width="80%" style="border-radius: 12px; border: 1px solid rgba(255,255,255,0.1); box-shadow: 0 10px 25px rgba(0,0,0,0.4);">
    Your browser does not support the video tag. You can <a href="demo video.mp4">watch the demo video here</a>.
  </video>
  
  <br />
  <br />

  *Place your walkthrough recording at `demo_video.mp4` in the project root folder to play it directly in the player above.*

</div>

---

## ⚡ Quick Start (1-Click Run)

PromptSQL contains a root-level orchestrator script `run.py` which automates virtual environment creation, dependencies installation (for both backend and frontend), frontend assets compilation, and launches the server.

Simply run the following in your root terminal:

```bash
python run.py
```

This will:
- Check for Python virtual environment (`venv`) and install missing requirements.
- Execute `npm install` inside the frontend directory.
- Build static frontend assets (`npm run build`).
- Start the unified FastAPI Server on **`http://127.0.0.1:8000`** serving both the API backend and the static client files.

---

## ⚙️ Environment Configuration

Create a `.env` file in the `/backend` directory. Provide your MySQL credentials and Groq API Key as shown below:

```ini
MYSQL_USER=root
MYSQL_PASSWORD=your_mysql_password
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DATABASE=promptsql_db
GROQ_API_KEY=gsk_your_actual_groq_api_key
```

---

## 🚀 Key Features

* **📁 Ingestion & Auto-Cleaning**: Supports CSV and Excel, scans datatypes (Dates, Floats, Strings), and normalizes column headers safely.
* **💬 Conversational NL-to-SQL**: Translates questions (e.g. *"Show me the top 5 brands by sales in 2025"*) into native SQL queries with a self-healing error correction loop.
* **🔒 Multi-User Session Isolation**: Isolates concurrent browser sessions completely using local storage IDs. Multiple users upload data and query tables independently without database conflicts.
* **🛡️ Natural Modifications with Impact Simulation**: Safely run INSERTS, UPDATES, or DELETES. The backend runs a dry-run estimation first, warns you of the row impact count, and requires manual confirmation before writing.
* **📄 Exporters**: Export raw query datasets directly to CSV, Excel, HTML, or formatted PDF layouts.

---

## 🔧 Manual Developer Setup

If you'd like to run frontend and backend separately for hot-reloading development environments:

### 1. Setup Backend
```bash
cd backend
python -m venv venv
# Activate virtual environment
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

pip install -r requirements.txt
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 2. Setup Frontend
```bash
cd frontend
npm install
npm run dev
```
The development frontend server will boot up at **`http://localhost:5173`**.

---

## 🛡️ Database Mutation Safety Protocol

| Stage | Security Layer | Action |
| :--- | :--- | :--- |
| **1. Keyword Scan** | Intent & SQL Validator | Rejects suspicious sub-queries, shell injection characters, or queries targeting core session tracking tables (`query_history`, `audit_logs`, `saved_reports`). |
| **2. Simulation** | Impact Estimator | Generates a virtual dry-run targeting `SELECT COUNT(*)` on active tables to determine exactly how many entries match the criteria. |
| **3. Verification** | AI Explainer & UI Alert | Generates a descriptive warning explaining exactly how many rows will be altered or deleted. |
| **4. Auditing** | Audit Logs & Transactions | Logs the query, user approving action, status, and outcome. Runs everything transactionally so it rolls back automatically on execution failures. |
