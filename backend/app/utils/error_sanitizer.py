import re
from typing import Any
from fastapi import HTTPException


def sanitize_error_message(msg: Any) -> str:
    """
    Sanitizes any string or exception message to completely strip out:
    1. Database connection URLs containing passwords, hosts, or ports.
    2. API keys (Groq, OpenAI, Google).
    3. Passwords, secrets, and auth tokens.
    4. Local absolute filesystem paths.
    """
    if not msg:
        return ""
    text = str(msg)

    # 1. Mask database connection URLs: mysql+pymysql://user:pass@host:port/db -> mysql+pymysql://***:***@[database-host]/[database]
    text = re.sub(
        r"(mysql(\+pymysql)?|postgresql(\+psycopg2)?|sqlite)://[^:@\s]+:[^@\s]+@[^\s/:]+(:[0-9]+)?/[^\s\?\"'\)]+",
        r"\1://***:***@[database-host]/[database]",
        text,
        flags=re.IGNORECASE
    )
    # Generic URL credentials masking: protocol://user:pass@host
    text = re.sub(r"://([^:@\s\"']+):([^@\s\"']+)@", r"://***:***@", text)

    # 2. Mask Groq API keys: gsk_...
    text = re.sub(r"gsk_[a-zA-Z0-9_\-]{10,}", "gsk_***", text)

    # 3. Mask Google / Gemini API keys: AIzaSy...
    text = re.sub(r"AIzaSy[a-zA-Z0-9_-]{20,}", "AIzaSy***", text)

    # 4. Mask Bearer authorization tokens
    text = re.sub(r"Bearer\s+[a-zA-Z0-9\._\-]{20,}", "Bearer ***", text, flags=re.IGNORECASE)

    # 5. Mask password assignments in queries or logs: password='...' or password="..." or password=...
    text = re.sub(
        r"(password|passwd|secret|jwt_secret|api_key)\s*[:=]\s*['\"][^'\"]+['\"]",
        r"\1=***",
        text,
        flags=re.IGNORECASE
    )

    # 6. Mask local filesystem absolute paths (Windows & Unix)
    text = re.sub(r"[A-Za-z]:\\(?:[a-zA-Z0-9_.\- ]+\\)+[a-zA-Z0-9_.\- ]*", r"[internal-source-path]", text)
    text = re.sub(r"/(Users|home|root|app)/[^:\n\r\t\"']+", r"[internal-source-path]", text)

    return text


def get_safe_exception_message(e: Exception, is_production: bool = False, context: str = "request") -> str:
    """
    Returns a safe error message suitable for API response payloads.
    In production, prevents stack traces or raw driver errors from reaching clients.
    """
    if isinstance(e, HTTPException):
        detail = e.detail
        if isinstance(detail, str):
            return sanitize_error_message(detail)
        return detail

    raw_str = str(e)
    sanitized = sanitize_error_message(raw_str)

    if is_production:
        lower_raw = raw_str.lower()
        # 1. Query timeout errors
        if any(t_err in lower_raw for t_err in ("3024", "max_execution_time", "statement execution time exceeded", "query execution was interrupted", "timed out", "timeout")):
            return "Query execution timed out. Please simplify your query or apply stricter filters."
        # 2. Result budget / cell size limit errors
        if any(s_err in lower_raw for s_err in ("cell size exceeds", "result cell exceeds", "maximum size limit", "result size limit", "byte budget")):
            return "The query result exceeds the maximum permitted size. Please refine your query filters."
        # 3. Database driver and syntax errors
        if any(db_err in lower_raw for db_err in (
            "operationalerror", "programmingerror", "databaseerror", "interfaceerror",
            "pymysql", "sqlalchemy", "mysql", "access denied", "can't connect",
            "table doesn't exist", "unknown column", "syntax error", "1054", "1146", "1064", "1792", "read-only", "lost connection"
        )):
            return "A database error occurred while processing your request. Please try again later."
        # 4. LLM service errors
        if any(llm_err in lower_raw for llm_err in ("groq", "ratelimit", "authenticationerror", "api key", "openai")):
            return "The AI Analytics service is currently unavailable. Please try again shortly."
        return f"An unexpected error occurred while processing your {context}."

    return sanitized
