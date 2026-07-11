import os

CONFIG_FILE = "active_table.txt"


def set_current_table(table_name: str):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(table_name)
    except Exception as e:
        print("Failed to save active table name:", e)


def get_current_table() -> str:
    if not os.path.exists(CONFIG_FILE):
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return f.read().strip() or None
    except Exception as e:
        print("Failed to load active table name:", e)
        return None