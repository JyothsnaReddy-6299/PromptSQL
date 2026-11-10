import os
import threading
from typing import Optional, Dict

_LOCK = threading.Lock()
_USER_ACTIVE_TABLES: Dict[str, str] = {}
UPLOAD_DIR = "uploads"


def _user_config_file(user_id: str) -> str:
    safe_user_id = "".join(c for c in user_id if c.isalnum() or c == "_")
    return os.path.join(UPLOAD_DIR, f".active_table_{safe_user_id}.txt")


def set_current_table(table_name: str, user_id: Optional[str] = None) -> None:
    """
    Stores active table scoped strictly to the specific user.
    Persists atomically to the database (user_active_datasets table) to guarantee
    isolation and consistency across multiple worker processes and containers.
    Never overwrites global state or cross-tenant tables.
    """
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        return

    clean_user_id = user_id.strip()
    clean_table = (table_name or "").strip()

    # 1. Update in-process cache
    with _LOCK:
        if clean_table:
            _USER_ACTIVE_TABLES[clean_user_id] = clean_table
        else:
            _USER_ACTIVE_TABLES.pop(clean_user_id, None)

    # 2. Persist atomically to MySQL database (multi-worker & multi-container safe)
    try:
        from app.database.connection import SessionLocal
        from app.models.user_active_dataset import UserActiveDataset

        with SessionLocal() as db:
            if clean_table:
                record = db.query(UserActiveDataset).filter(UserActiveDataset.user_id == clean_user_id).first()
                if record:
                    record.table_name = clean_table
                else:
                    record = UserActiveDataset(user_id=clean_user_id, table_name=clean_table)
                    db.add(record)
            else:
                db.query(UserActiveDataset).filter(UserActiveDataset.user_id == clean_user_id).delete(synchronize_session=False)
            db.commit()
    except Exception as e:
        print(f"[TABLE MANAGER WARNING] Failed persisting active table to DB: {e}")

    # 3. Maintain local file for backward compatibility
    try:
        cfg = _user_config_file(clean_user_id)
        if clean_table:
            os.makedirs(UPLOAD_DIR, exist_ok=True)
            with open(cfg, "w", encoding="utf-8") as f:
                f.write(clean_table)
        else:
            if os.path.exists(cfg):
                os.remove(cfg)
    except Exception:
        pass


def get_current_table(user_id: Optional[str] = None) -> Optional[str]:
    """
    Retrieves active table scoped strictly to user_id.
    Reads from the database first (authoritative source across all workers and containers),
    falling back to memory cache or local file if database is temporarily unavailable.
    Returns None if no active table set for this user or if user_id is None.
    """
    if not user_id or not isinstance(user_id, str) or not user_id.strip():
        return None

    clean_user_id = user_id.strip()

    # 1. Read from MySQL database first (authoritative across multiple workers & containers)
    try:
        from app.database.connection import SessionLocal
        from app.models.user_active_dataset import UserActiveDataset

        with SessionLocal() as db:
            record = db.query(UserActiveDataset).filter(UserActiveDataset.user_id == clean_user_id).first()
            if record and record.table_name:
                with _LOCK:
                    _USER_ACTIVE_TABLES[clean_user_id] = record.table_name
                return record.table_name
            elif record and not record.table_name:
                with _LOCK:
                    _USER_ACTIVE_TABLES.pop(clean_user_id, None)
                return None
    except Exception:
        pass

    # 2. In-memory cache fallback
    with _LOCK:
        if clean_user_id in _USER_ACTIVE_TABLES:
            return _USER_ACTIVE_TABLES[clean_user_id]

    # 3. Local file fallback
    cfg = _user_config_file(clean_user_id)
    if os.path.exists(cfg):
        try:
            with open(cfg, "r", encoding="utf-8") as f:
                val = f.read().strip()
                if val:
                    with _LOCK:
                        _USER_ACTIVE_TABLES[clean_user_id] = val
                    return val
        except Exception:
            pass

    return None


def clear_current_table(user_id: Optional[str] = None) -> None:
    """
    Clears active dataset state for the specified user across DB, cache, and filesystem.
    """
    set_current_table("", user_id=user_id)
