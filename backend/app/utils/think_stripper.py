import re

def strip_think_blocks(text: str) -> str:
    """
    Strips <think>...</think> blocks from LLM output, including any unclosed <think> tags.
    """
    if not text:
        return text
    # Remove closed <think>...</think> blocks (case-insensitive, dotall)
    cleaned = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove any unclosed <think> block at the end of output
    cleaned = re.sub(r'<think>.*', '', cleaned, flags=re.DOTALL | re.IGNORECASE)
    return cleaned.strip()
