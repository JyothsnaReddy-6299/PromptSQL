import os
import threading
from typing import Optional, Dict

_LOCK = threading.Lock()
_USER_ACTIVE_TABLES: Dict[str, str] = {}
UPLOAD_DIR = "uploads"


def _user_config_file(user_id: str) -> str:
    safe_user_id = "".join(c for c in user_id if c.isalnum() or c == "_")
    return os.path.join(UPLOAD_DIR, f".active_table_{safe_user_id}.txt")


def set_current_table(table_name: str, user_id: Optional[str] = None):
    """
    Stores active table scoped to the specific user.
    Never overwrites global state or cross-tenant tables.
    """
    with _LOCK:
        if user_id:
            _USER_ACTIVE_TABLES[user_id] = table_name
            try:
                os.makedirs(UPLOAD_DIR, exist_ok=True)
                with open(_user_config_file(user_id), "w", encoding="utf-8") as f:
                    f.write(table_name)
            except Exception as e:
                print("Failed to save user active table name:", e)


def get_current_table(user_id: Optional[str] = None) -> Optional[str]:
    """
    Retrieves active table scoped to user_id.
    Returns None if no active table set for this user.
    """
    with _LOCK:
        if user_id:
            if user_id in _USER_ACTIVE_TABLES:
                return _USER_ACTIVE_TABLES[user_id]
            cfg = _user_config_file(user_id)
            if os.path.exists(cfg):
                try:
                    with open(cfg, "r", encoding="utf-8") as f:
                        val = f.read().strip()
                        if val:
                            _USER_ACTIVE_TABLES[user_id] = val
                            return val
                except Exception as e:
                    print("Failed to load user active table name:", e)
            return None
        return None
