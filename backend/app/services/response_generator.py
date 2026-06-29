def generate_response(question, records):

    if len(records) == 0:
        return "No matching records found."

    first_row = records[0]

    first_column = list(first_row.keys())[0]

    values = [str(row[first_column]) for row in records]

    if len(values) <= 10:

        return (
            f"{question.capitalize()}:\n"
            + ", ".join(values)
        )

    preview = ", ".join(values[:10])

    remaining = len(values) - 10

    return (
        f"{question.capitalize()}:\n"
        f"{preview} and {remaining} more."
    )