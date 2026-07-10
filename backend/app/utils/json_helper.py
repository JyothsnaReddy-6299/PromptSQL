import datetime
from decimal import Decimal


def sanitize_for_json(data):
    """
    Recursively converts non-serializable database types (like Decimals and dates)
    into standard JSON-safe types.
    """
    if isinstance(data, list):
        return [sanitize_for_json(item) for item in data]
    elif isinstance(data, dict):
        return {key: sanitize_for_json(val) for key, val in data.items()}
    elif isinstance(data, Decimal):
        return float(data)
    elif isinstance(data, (datetime.date, datetime.datetime)):
        return data.isoformat()
    return data
