def is_analytical(question):

    question = question.lower()

    analytical_words = [

        "summary",
        "summarize",
        "analyse",
        "analyze",
        "trend",
        "insight",
        "compare",
        "highest",
        "lowest",
        "average",
        "maximum",
        "minimum",
        "forecast",
        "why",
        "performance"

    ]

    return any(word in question for word in analytical_words)