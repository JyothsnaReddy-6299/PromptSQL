import os
from groq import Groq
from dotenv import load_dotenv
from app.utils.think_stripper import strip_think_blocks

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
env_path = os.path.join(base_dir, ".env")
if os.path.exists(env_path):
    load_dotenv(env_path, override=True)
load_dotenv(override=True)

DEFAULT_MODEL = "qwen/qwen3.8-27b"


def get_current_model() -> str:
    """
    Returns the configured Groq model, falling back to qwen/qwen3.8-27b.
    Auto-corrects outdated model name 'qwen3.6-27b' to 'qwen3.8-27b'.
    """
    model = (os.getenv("GROQ_MODEL") or DEFAULT_MODEL).strip().strip("'\"")
    if "qwen3.6" in model.lower():
        model = DEFAULT_MODEL
    return model


def call_llm(system_prompt: str, user_prompt: str, temperature: float = 0.1) -> str:
    """
    Calls the configured Groq LLM model.
    """
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key or not api_key.strip():
        raise Exception("GROQ_API_KEY is not configured in environment variables.")

    model = get_current_model()

    try:
        client = Groq(api_key=api_key.strip())
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
        print(f"[LLM Service] Groq API call failed with model '{model}': {e}")
        raise e
