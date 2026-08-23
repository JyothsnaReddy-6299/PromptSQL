import os
from groq import Groq
from dotenv import load_dotenv
from app.utils.think_stripper import strip_think_blocks

load_dotenv()

# Groq Configurations
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
    """
    Calls the configured Groq LLM model.
    """
    if not GROQ_API_KEY or not GROQ_API_KEY.strip():
        raise Exception("GROQ_API_KEY is not configured in environment variables.")

    try:
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
    except Exception as e:
        print(f"[LLM Service] Groq API call failed: {e}")
        raise e
