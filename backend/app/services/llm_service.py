from groq import Groq
from app.core.config import get_settings
from app.utils.think_stripper import strip_think_blocks
from app.utils.error_sanitizer import sanitize_error_message


def get_current_model() -> str:
    """
    Returns the configured Groq model from centralized settings.
    """
    settings = get_settings()
    return settings.GROQ_MODEL


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
    """
    Calls the configured Groq LLM model using server-side credentials exclusively.
    Sanitizes any provider exceptions before propagation to prevent secret exposure.
    """
    settings = get_settings()
    api_key = (settings.GROQ_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured in backend environment variables.")

    model = get_current_model()

    try:
        client = Groq(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=temperature
        )
        raw_text = response.choices[0].message.content.strip()
        return strip_think_blocks(raw_text)
    except Exception as e:
        safe_msg = sanitize_error_message(str(e))
        print(f"[LLM Service] Groq API call failed with model '{model}': {safe_msg}")
        raise RuntimeError(f"AI Analytics service error: {safe_msg}") from None
