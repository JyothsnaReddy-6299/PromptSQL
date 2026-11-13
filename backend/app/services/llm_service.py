import time
import groq
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


def call_llm(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.1,
    max_tokens: int = 500
) -> str:
    """
    Calls the configured Groq LLM model using server-side credentials exclusively.
    Sanitizes any provider exceptions before propagation to prevent secret exposure.
    Enforces a bounded output token limit (max_tokens=500) to operate safely within
    provider rate limits, with exponential backoff on transient RateLimitError.
    """
    settings = get_settings()
    api_key = (settings.GROQ_API_KEY or "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY is not configured in backend environment variables.")

    model = get_current_model()
    client = Groq(api_key=api_key)

    max_retries = 3
    base_delay = 2.0

    for attempt in range(max_retries):
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            raw_text = response.choices[0].message.content.strip()
            return strip_think_blocks(raw_text)
        except groq.RateLimitError as rle:
            if attempt < max_retries - 1:
                sleep_sec = base_delay * (2 ** attempt)
                print(f"[LLM Service] Rate limit hit on model '{model}'. Retrying in {sleep_sec:.1f}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(sleep_sec)
                continue

            # Fallback to secondary model if primary model exhausted rate limit
            fallback_models = ["openai/gpt-oss-20b", "openai/gpt-oss-120b"]
            for fb_model in fallback_models:
                if fb_model != model:
                    try:
                        print(f"[LLM Service] Primary model '{model}' rate-limited. Falling back to '{fb_model}'...")
                        response = client.chat.completions.create(
                            model=fb_model,
                            messages=[
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt}
                            ],
                            temperature=temperature,
                            max_tokens=max_tokens
                        )
                        raw_text = response.choices[0].message.content.strip()
                        return strip_think_blocks(raw_text)
                    except Exception as fb_err:
                        print(f"[LLM Service] Fallback model '{fb_model}' failed: {sanitize_error_message(str(fb_err))}")
                        continue

            safe_msg = sanitize_error_message(str(rle))
            print(f"[LLM Service] Groq API call failed with model '{model}': {safe_msg}")
            raise RuntimeError(f"AI Analytics service error: {safe_msg}") from None
        except Exception as e:
            safe_msg = sanitize_error_message(str(e))
            print(f"[LLM Service] Groq API call failed with model '{model}': {safe_msg}")
            raise RuntimeError(f"AI Analytics service error: {safe_msg}") from None
