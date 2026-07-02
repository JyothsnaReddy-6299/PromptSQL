from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found.")

client = Groq(api_key=api_key)


def classify_question(question: str) -> str:
    """
    Classifies a user question into one of:
    - retrieval
    - analytical
    - insight
    """

    prompt = f"""
You are an intent classifier for an AI Data Analytics Platform.

Your job is to classify the user's question into EXACTLY ONE category.

Categories:

1. retrieval
The user wants rows or specific values from the dataset.

Examples:
- Show all employees
- List employee IDs
- Display customer names
- Give order IDs whose category is Furniture
- Show salaries greater than 50000

2. analytical
The user wants calculations or aggregations.

Examples:
- Average salary
- Highest sales
- Lowest price
- Count employees
- Which region has the highest sales?
- Total revenue
- Top 5 products

3. insight
The user wants explanations, trends, patterns or observations.

Examples:
- Give insights about the dataset
- Analyze sales
- Explain the trends
- Summarize employee performance

Rules:
- Return ONLY ONE WORD.
- Return exactly one of:
retrieval
analytical
insight

Question:
{question}
"""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {
                "role": "system",
                "content": "You classify user questions."
            },
            {
                "role": "user",
                "content": prompt
            }
        ]
    )

    category = response.choices[0].message.content.strip().lower()

    if category not in ["retrieval", "analytical", "insight"]:
        category = "retrieval"

    return category