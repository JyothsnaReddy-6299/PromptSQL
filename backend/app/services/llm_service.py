import os
import httpx
from groq import Groq
from dotenv import load_dotenv
from app.utils.think_stripper import strip_think_blocks

load_dotenv()

# Gemini Configurations
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

# Groq Configurations
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "qwen/qwen3.6-27b")

def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
    """
    Calls the configured LLM (Gemini if GEMINI_API_KEY is present, fallback to Groq).
    """
    if GEMINI_API_KEY and GEMINI_API_KEY.strip():
        try:
            # Call Gemini via official REST API
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            
            payload = {
                "contents": [
                    {
                        "role": "user",
                        "parts": [{"text": user_prompt}]
                    }
                ],
                "systemInstruction": {
                    "parts": [{"text": system_prompt}]
                },
                "generationConfig": {
                    "temperature": temperature
                }
            }
            
            with httpx.Client() as client:
                res = client.post(url, json=payload, timeout=30.0)
                res.raise_for_status()
                res_data = res.json()
                
                candidates = res_data.get("candidates", [])
                if candidates:
                    content = candidates[0].get("content", {})
                    parts = content.get("parts", [])
                    if parts:
                        text = parts[0].get("text", "")
                        return strip_think_blocks(text)
                        
                raise Exception("Empty response from Gemini API")
        except Exception as e:
            print(f"[LLM Service] Gemini API call failed: {e}. Falling back to Groq...")
            # Fall through to Groq fallback

    if not GROQ_API_KEY:
        raise Exception("No active LLM API key configured (neither GEMINI_API_KEY nor GROQ_API_KEY found).")
        
    client = Groq(api_key=GROQ_API_KEY)
    response = client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=temperature
    )
    raw_text = response.choices[0].message.content.strip()
    return strip_think_blocks(raw_text)
