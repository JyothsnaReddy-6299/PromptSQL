from groq import Groq
import os
from dotenv import load_dotenv

load_dotenv()
api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found.")

client = Groq(api_key=api_key)


def detect_intent(question: str) -> str:
    """
    Classifies a natural language query into one of:
    SELECT, INSERT, UPDATE, DELETE, MERGE, CREATE, ALTER, DROP, RENAME, TRUNCATE.
    """
    prompt = f"""
    You are an expert SQL intent classifier.
    Classify the following natural language request into EXACTLY ONE of the following SQL intents:
    - SELECT (for retrieving, reading, querying, summarizing, or viewing data)
    - INSERT (for adding, appending, inserting new records or rows)
    - UPDATE (for modifying, updating, changing values of existing records or rows)
    - DELETE (for removing, deleting, erasing records or rows)
    - MERGE (for merging, upserting records)
    - CREATE (for creating tables, indexes, schemas)
    - ALTER (for modifying table structure, adding columns, changing types)
    - DROP (for deleting, dropping tables permanently)
    - RENAME (for renaming tables or columns)
    - TRUNCATE (for clearing, truncating, emptying tables)

    User Request: "{question}"

    Return ONLY the uppercase word of the intent. Do not include quotes, markdown, explanations, or any other words.
    Example output: UPDATE
    """

    try:
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": "You are a precise SQL intent classifier. Output ONLY the uppercase intent word."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            temperature=0.0
        )
        
        intent = response.choices[0].message.content.strip().upper()
        valid_intents = ["SELECT", "INSERT", "UPDATE", "DELETE", "MERGE", "CREATE", "ALTER", "DROP", "RENAME", "TRUNCATE"]
        
        if intent not in valid_intents:
            # Fallback based on keywords
            q_lower = question.lower()
            if any(w in q_lower for w in ["select", "show", "get", "list", "display", "find"]):
                return "SELECT"
            if any(w in q_lower for w in ["insert", "add", "append"]):
                return "INSERT"
            if any(w in q_lower for w in ["update", "modify", "change", "set"]):
                return "UPDATE"
            if any(w in q_lower for w in ["delete", "remove", "erase"]):
                return "DELETE"
            if any(w in q_lower for w in ["drop"]):
                return "DROP"
            if any(w in q_lower for w in ["truncate", "clear", "empty"]):
                return "TRUNCATE"
            if any(w in q_lower for w in ["alter", "add column", "drop column"]):
                return "ALTER"
            if any(w in q_lower for w in ["create"]):
                return "CREATE"
            if any(w in q_lower for w in ["rename"]):
                return "RENAME"
            return "SELECT"
        return intent
    except Exception as e:
        print("Intent detection error:", e)
        return "SELECT"
