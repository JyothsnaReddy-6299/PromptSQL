import time
from typing import List, Dict, Any, Optional, Callable
import groq
from groq import Groq
from app.core.config import get_settings
from app.utils.think_stripper import strip_think_blocks
from app.utils.error_sanitizer import sanitize_error_message


# Outgoing AI boundary payload recorder for audit & verification
_OUTGOING_PAYLOADS_LOG: List[Dict[str, Any]] = []
_MOCK_AI_HANDLER: Optional[Callable[[str, str, Dict[str, Any]], str]] = None


def get_recorded_ai_payloads() -> List[Dict[str, Any]]:
    """Returns a shallow copy of all outgoing payloads recorded at the AI boundary."""
    return list(_OUTGOING_PAYLOADS_LOG)


def clear_recorded_ai_payloads() -> None:
    """Clears the recorded outgoing AI payload log."""
    global _OUTGOING_PAYLOADS_LOG
    _OUTGOING_PAYLOADS_LOG.clear()


def set_mock_ai_handler(handler: Optional[Callable[[str, str, Dict[str, Any]], str]]) -> None:
    """Sets a mock AI provider handler for testing that receives (system_prompt, user_prompt, payload_record)."""
    global _MOCK_AI_HANDLER
    _MOCK_AI_HANDLER = handler


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
    Guaranteed by Privacy Guardian: Intercepts and sanitizes all prompts before transmission.
    Records outgoing payloads at the AI boundary for privacy verification.
    """
    # 1. Enforce Centralized Privacy Guardian AI Boundary Redaction
    try:
        from app.services.privacy_redactor import redact_text_for_ai
        safe_system_prompt, sys_redactions = redact_text_for_ai(system_prompt)
        safe_user_prompt, user_redactions = redact_text_for_ai(user_prompt)
    except Exception as redaction_err:
        # Fail closed: never transmit uninspected prompts if privacy redaction fails
        raise RuntimeError(f"Privacy Guardian enforcement failed: {redaction_err}") from redaction_err

    # 1.1 Fail-closed boundary check: verify no raw canary values escape to AI provider (Issue 16.1)
    combined_outgoing = f"{safe_system_prompt}\n{safe_user_prompt}"
    canary_leak_checks = [
        "privacy.canary",
        "@example.invalid",
        "987654321001",
        "TESTA1234A",
        "+1-202-555-0100"
    ]
    for canary in canary_leak_checks:
        if canary.lower() in combined_outgoing.lower():
            raise RuntimeError(
                f"Privacy Guardian boundary violation: Protected canary value '{canary}' "
                "detected in outgoing AI payload. Failing closed."
            )

    payload_record = {
        "timestamp": time.time(),
        "model": get_current_model(),
        "system_prompt": safe_system_prompt,
        "user_prompt": safe_user_prompt,
        "messages": [
            {"role": "system", "content": safe_system_prompt},
            {"role": "user", "content": safe_user_prompt}
        ],
        "redactions_count": sys_redactions + user_redactions,
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    _OUTGOING_PAYLOADS_LOG.append(payload_record)

    # 2. Check for Mock Provider Handler (Used in automated tests & offline environments)
    if _MOCK_AI_HANDLER is not None:
        mock_res = _MOCK_AI_HANDLER(safe_system_prompt, safe_user_prompt, payload_record)
        return strip_think_blocks(mock_res).strip()

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
                    {"role": "system", "content": safe_system_prompt},
                    {"role": "user", "content": safe_user_prompt}
                ],
                temperature=temperature,
                max_tokens=max_tokens
            )
            raw_text = response.choices[0].message.content.strip()
            cleaned = strip_think_blocks(raw_text)
            if cleaned:
                return cleaned

            # If cleaned is empty, the model was cut off inside unclosed <think> tags
            print(f"[LLM Service] Model '{model}' output was truncated inside <think> tags. Trying alternative non-reasoning model...")
            fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
            for fb_model in fallback_models:
                if fb_model != model:
                    try:
                        response = client.chat.completions.create(
                            model=fb_model,
                            messages=[
                                {"role": "system", "content": safe_system_prompt},
                                {"role": "user", "content": safe_user_prompt}
                            ],
                            temperature=temperature,
                            max_tokens=max_tokens
                        )
                        fb_text = response.choices[0].message.content.strip()
                        fb_cleaned = strip_think_blocks(fb_text)
                        if fb_cleaned:
                            return fb_cleaned
                    except Exception as fb_err:
                        print(f"[LLM Service] Fallback model '{fb_model}' failed: {sanitize_error_message(str(fb_err))}")
                        continue

            return raw_text
        except groq.RateLimitError as rle:
            if attempt < max_retries - 1:
                sleep_sec = base_delay * (2 ** attempt)
                print(f"[LLM Service] Rate limit hit on model '{model}'. Retrying in {sleep_sec:.1f}s (attempt {attempt + 1}/{max_retries})...")
                time.sleep(sleep_sec)
                continue

            # Fallback to secondary model if primary model exhausted rate limit
            fallback_models = ["openai/gpt-oss-120b", "openai/gpt-oss-20b"]
            for fb_model in fallback_models:
                if fb_model != model:
                    try:
                        print(f"[LLM Service] Primary model '{model}' rate-limited. Falling back to '{fb_model}'...")
                        response = client.chat.completions.create(
                            model=fb_model,
                            messages=[
                                {"role": "system", "content": safe_system_prompt},
                                {"role": "user", "content": safe_user_prompt}
                            ],
                            temperature=temperature,
                            max_tokens=max_tokens
                        )
                        raw_text = response.choices[0].message.content.strip()
                        cleaned_fb = strip_think_blocks(raw_text)
                        if cleaned_fb:
                            return cleaned_fb
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
