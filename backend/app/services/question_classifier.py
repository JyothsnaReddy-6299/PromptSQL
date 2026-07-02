from groq import Groq
from dotenv import load_dotenv
import os

load_dotenv()

api_key = os.getenv("GROQ_API_KEY")

if not api_key:
    raise Exception("GROQ_API_KEY not found.")

client = Groq(api_key=api_key)


VALID_TYPES = {
    "retrieval",
    "analytical",
    "insight"
}


def classify_question(question: str) -> str:
    """
    Classifies the user's question into one of:
    - retrieval
    - analytical
    - insight
    """

    prompt = f"""
You are an expert intent classifier for an AI-powered Data Analytics platform.

Your ONLY task is to classify the user's question into EXACTLY ONE of these categories.

------------------------------------
1. retrieval
------------------------------------
The user wants to retrieve existing records.

Examples:

- Show all employees
- List employee IDs
- Display customer names
- Give order IDs
- Show salaries
- Show employees whose department is HR
- List products costing more than 500
- Display female employees

------------------------------------
2. analytical
------------------------------------
The user wants calculations or aggregations.

Examples:

- Average salary
- Total sales
- Highest salary
- Lowest price
- Count employees
- Which region has the highest sales?
- Top 10 customers
- Department with maximum employees
- Monthly revenue
- Sum of sales

------------------------------------
3. insight
------------------------------------
The user wants explanations, observations or trends.

Examples:

- Give insights
- Analyze the dataset
- Explain sales performance
- Summarize employee data
- What trends do you observe?
- Describe the dataset

------------------------------------

Rules

Return ONLY one word.

Allowed outputs:

retrieval

analytical

insight

Question:

{question}
"""

    try:

        response = client.chat.completions.create(

            model="llama-3.3-70b-versatile",

            messages=[

                {
                    "role": "system",
                    "content": (
                        "You are an intent classifier. "
                        "Return only one word."
                    )
                },

                {
                    "role": "user",
                    "content": prompt
                }

            ]

        )

        result = (
            response
            .choices[0]
            .message
            .content
            .strip()
            .lower()
        )

        if result not in VALID_TYPES:
            result = "retrieval"

        return result

    except Exception:

        # Safe fallback
        return "retrieval"